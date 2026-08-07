/************************************************************************
 **
 **  Agent-safe JSON command boundary for garment-cad-mcp.
 **  Copyright (C) 2026 garment-cad-mcp contributors.
 **
 **  This file is distributed under the same GPL-3.0-or-later terms as
 **  Valentina.  It deliberately delegates construction to native tools.
 **
 *************************************************************************/

#include "vcommandservice.h"

#include "../mainwindow.h"
#include "../vmisc/def.h"
#include "../vmisc/vabstractvalapplication.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolarc.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolabstractcurve.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolspline.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoollineintersect.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoolendline.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoolalongline.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolbasepoint.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolsinglepoint.h"
#include "../vtools/tools/drawTools/vtoolline.h"
#include "../vtools/tools/vinteractivetool.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QSaveFile>
#include <QTextStream>
#include <QUuid>

#include <stdexcept>

namespace
{
auto EmptySummary() -> QJsonObject
{
    return {{QStringLiteral("created"), QJsonArray{}},
            {QStringLiteral("changed"), QJsonArray{}},
            {QStringLiteral("deleted"), QJsonArray{}},
            {QStringLiteral("measurements"), QJsonObject{}},
            {QStringLiteral("issues"), QJsonArray{}}};
}

auto RequiredString(const QJsonObject &object, const QString &name) -> QString
{
    const QString value = object.value(name).toString();
    if (value.isEmpty())
    {
        throw std::invalid_argument(QStringLiteral("Missing string field: %1").arg(name).toStdString());
    }
    return value;
}

auto NativeFormulaForMillimetres(qreal value) -> QString
{
    const qreal converted = UnitConvertor(value, Unit::Mm, VAbstractValApplication::VApp()->patternUnits());
    return QString::number(converted, 'g', 15);
}
} // namespace

//---------------------------------------------------------------------------------------------------------------------
VCommandService::VCommandService(MainWindow *window)
  : m_window(window)
{
    if (m_window == nullptr)
    {
        throw std::invalid_argument("VCommandService requires a MainWindow");
    }
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::RunOnce() -> int
{
    QFile input;
    if (!input.open(stdin, QIODevice::ReadOnly))
    {
        return 1;
    }
    QFile output;
    if (!output.open(stdout, QIODevice::WriteOnly))
    {
        return 1;
    }

    QJsonObject response;
    int exitCode = 0;
    try
    {
        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(input.readAll(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject())
        {
            throw std::invalid_argument(QStringLiteral("Invalid JSON request: %1").arg(parseError.errorString())
                                            .toStdString());
        }
        response = Dispatch(document.object());
        response.insert(QStringLiteral("ok"), true);
    }
    catch (const std::exception &error)
    {
        response = {{QStringLiteral("ok"), false},
                    {QStringLiteral("error"),
                     QJsonObject{{QStringLiteral("code"), QStringLiteral("command_failed")},
                                 {QStringLiteral("message"), QString::fromUtf8(error.what())}}}};
        exitCode = 1;
    }

    output.write(QJsonDocument(response).toJson(QJsonDocument::Compact));
    output.write("\n");
    output.flush();
    return exitCode;
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::Dispatch(const QJsonObject &request) -> QJsonObject
{
    const QString method = RequiredString(request, QStringLiteral("method"));
    if (method == QStringLiteral("service.info"))
    {
        return {{QStringLiteral("protocol_version"), QStringLiteral("1.0")},
                {QStringLiteral("application"), QStringLiteral("Valentina")},
                {QStringLiteral("units"), QStringLiteral("mm")},
                {QStringLiteral("preview_commit"), true},
                {QStringLiteral("handlers"),
                 QJsonArray{QStringLiteral("pattern.object_get"), QStringLiteral("pattern.base_point"),
                            QStringLiteral("pattern.object_update"), QStringLiteral("pattern.object_delete"),
                            QStringLiteral("pattern.end_line"), QStringLiteral("pattern.line"),
                            QStringLiteral("pattern.along_line"), QStringLiteral("pattern.midpoint"),
                            QStringLiteral("pattern.line_intersect"), QStringLiteral("pattern.arc"),
                            QStringLiteral("pattern.spline")}}};
    }
    if (method == QStringLiteral("commands.preview"))
    {
        return Preview(request);
    }
    if (method == QStringLiteral("commands.commit"))
    {
        return Commit(request);
    }
    throw std::invalid_argument(QStringLiteral("Unknown method: %1").arg(method).toStdString());
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::Preview(const QJsonObject &request) -> QJsonObject
{
    const QString projectRoot = QDir::cleanPath(RequiredString(request, QStringLiteral("project_root")));
    const QString changeSetId = RequiredString(request, QStringLiteral("change_set_id"));
    ValidateChangeSetId(changeSetId);

    const QString sourcePattern = QDir(projectRoot).filePath(QStringLiteral("pattern/main.val"));
    if (!QFileInfo::exists(sourcePattern))
    {
        throw std::invalid_argument("The project does not contain pattern/main.val");
    }

    const QString candidateRoot = CandidateRoot(projectRoot, changeSetId);
    const QString candidatePattern = QDir(candidateRoot).filePath(QStringLiteral("pattern/main.val"));
    QDir().mkpath(QFileInfo(candidatePattern).absolutePath());
    AtomicCopy(sourcePattern, candidatePattern);

    const QString sourceAliases = QDir(projectRoot).filePath(QStringLiteral(".garmentcad/aliases.json"));
    QJsonObject aliases = ReadJsonFile(sourceAliases);
    if (!aliases.contains(QStringLiteral("objects")))
    {
        aliases.insert(QStringLiteral("objects"), QJsonObject{});
    }

    if (!m_window->LoadPattern(candidatePattern))
    {
        throw std::runtime_error("Valentina could not open the candidate pattern");
    }

    QJsonObject summary = EmptySummary();
    for (const QJsonValue value : request.value(QStringLiteral("operations")).toArray())
    {
        if (!value.isObject())
        {
            throw std::invalid_argument("Operation must be an object");
        }
        ApplyOperation(value.toObject(), aliases, summary);
    }

    QString saveError;
    if (!m_window->SavePattern(candidatePattern, saveError))
    {
        throw std::runtime_error(QStringLiteral("Unable to save candidate: %1").arg(saveError).toStdString());
    }

    const QString candidateAliases = QDir(candidateRoot).filePath(QStringLiteral("aliases.json"));
    WriteJsonFile(candidateAliases, aliases);
    return {{QStringLiteral("summary"), summary},
            {QStringLiteral("resources"),
             QJsonArray{QStringLiteral("garment://changeset/%1/pattern").arg(changeSetId),
                        QStringLiteral("garment://changeset/%1/aliases").arg(changeSetId)}}};
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::Commit(const QJsonObject &request) -> QJsonObject
{
    const QString projectRoot = QDir::cleanPath(RequiredString(request, QStringLiteral("project_root")));
    const QString changeSetId = RequiredString(request, QStringLiteral("change_set_id"));
    ValidateChangeSetId(changeSetId);

    const QString candidateRoot = CandidateRoot(projectRoot, changeSetId);
    AtomicCopy(QDir(candidateRoot).filePath(QStringLiteral("pattern/main.val")),
               QDir(projectRoot).filePath(QStringLiteral("pattern/main.val")));
    AtomicCopy(QDir(candidateRoot).filePath(QStringLiteral("aliases.json")),
               QDir(projectRoot).filePath(QStringLiteral(".garmentcad/aliases.json")));
    return {{QStringLiteral("change_set_id"), changeSetId}};
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::ApplyOperation(const QJsonObject &operation, QJsonObject &aliases, QJsonObject &summary) -> void
{
    const QString action = RequiredString(operation, QStringLiteral("action"));
    const QJsonObject arguments = operation.value(QStringLiteral("arguments")).toObject();

    if (action == QStringLiteral("pattern.object_get"))
    {
        const quint32 nativeId = ResolveObject(operation.value(QStringLiteral("target")).toObject(), aliases);
        const auto object = m_window->pattern->GetGObject(nativeId);
        QJsonArray changed = summary.value(QStringLiteral("changed")).toArray();
        changed.append(QJsonObject{{QStringLiteral("uuid"), QJsonValue::Null},
                                   {QStringLiteral("alias"), object->name()}});
        summary.insert(QStringLiteral("changed"), changed);
        return;
    }

    if (action == QStringLiteral("pattern.object_delete"))
    {
        const QJsonObject reference = operation.value(QStringLiteral("target")).toObject();
        const quint32 nativeId = ResolveObject(reference, aliases);
        auto *tool = qobject_cast<VInteractiveTool *>(VAbstractPattern::getTool(nativeId));
        if (tool == nullptr)
        {
            throw std::invalid_argument("Object is not an interactive Valentina tool");
        }
        if (tool->IsRemovable() != RemoveStatus::Removable)
        {
            AddIssue(summary, QStringLiteral("error"), QStringLiteral("object_has_dependencies"),
                     QStringLiteral("Tool %1 cannot be deleted because it has dependencies").arg(nativeId));
            return;
        }
        tool->PerformDelete();

        QJsonObject objects = aliases.value(QStringLiteral("objects")).toObject();
        QJsonArray deleted = summary.value(QStringLiteral("deleted")).toArray();
        for (auto iterator = objects.begin(); iterator != objects.end(); ++iterator)
        {
            QJsonObject record = iterator.value().toObject();
            if (static_cast<quint32>(record.value(QStringLiteral("native_id")).toInteger()) == nativeId &&
                !record.value(QStringLiteral("deleted")).toBool())
            {
                record.insert(QStringLiteral("deleted"), true);
                iterator.value() = record;
                deleted.append(QJsonObject{{QStringLiteral("uuid"), iterator.key()},
                                           {QStringLiteral("alias"), record.value(QStringLiteral("alias"))}});
            }
        }
        aliases.insert(QStringLiteral("objects"), objects);
        summary.insert(QStringLiteral("deleted"), deleted);
        return;
    }

    if (action == QStringLiteral("pattern.object_update"))
    {
        const quint32 nativeId = ResolveObject(operation.value(QStringLiteral("target")).toObject(), aliases);
        auto *tool = qobject_cast<VInteractiveTool *>(VAbstractPattern::getTool(nativeId));
        if (tool == nullptr)
        {
            throw std::invalid_argument("Object is not an interactive Valentina tool");
        }

        if (auto *point = qobject_cast<VToolSinglePoint *>(tool); point != nullptr &&
            arguments.contains(QStringLiteral("name")))
        {
            point->setName(RequiredString(arguments, QStringLiteral("name")));
        }
        if (auto *basePoint = qobject_cast<VToolBasePoint *>(tool); basePoint != nullptr &&
            (arguments.contains(QStringLiteral("x_mm")) || arguments.contains(QStringLiteral("y_mm"))))
        {
            QPointF position = basePoint->GetBasePointPos();
            if (arguments.contains(QStringLiteral("x_mm")))
            {
                position.setX(UnitConvertor(arguments.value(QStringLiteral("x_mm")).toDouble(), Unit::Mm,
                                            VAbstractValApplication::VApp()->patternUnits()));
            }
            if (arguments.contains(QStringLiteral("y_mm")))
            {
                position.setY(UnitConvertor(arguments.value(QStringLiteral("y_mm")).toDouble(), Unit::Mm,
                                            VAbstractValApplication::VApp()->patternUnits()));
            }
            basePoint->SetBasePointPos(position);
        }
        if (auto *line = qobject_cast<VToolLine *>(tool); line != nullptr)
        {
            if (arguments.contains(QStringLiteral("line_type")))
            {
                line->SetLineType(RequiredString(arguments, QStringLiteral("line_type")));
            }
            if (arguments.contains(QStringLiteral("line_color")))
            {
                line->SetLineColor(RequiredString(arguments, QStringLiteral("line_color")));
            }
        }
        if (auto *curve = qobject_cast<VToolAbstractCurve *>(tool); curve != nullptr)
        {
            if (arguments.contains(QStringLiteral("line_type")))
            {
                curve->SetPenStyle(RequiredString(arguments, QStringLiteral("line_type")));
            }
            if (arguments.contains(QStringLiteral("line_color")))
            {
                curve->SetLineColor(RequiredString(arguments, QStringLiteral("line_color")));
            }
        }

        QJsonObject objects = aliases.value(QStringLiteral("objects")).toObject();
        QJsonArray changed = summary.value(QStringLiteral("changed")).toArray();
        for (auto iterator = objects.begin(); iterator != objects.end(); ++iterator)
        {
            QJsonObject record = iterator.value().toObject();
            if (static_cast<quint32>(record.value(QStringLiteral("native_id")).toInteger()) == nativeId &&
                !record.value(QStringLiteral("deleted")).toBool())
            {
                if (arguments.contains(QStringLiteral("alias")))
                {
                    record.insert(QStringLiteral("alias"), RequiredString(arguments, QStringLiteral("alias")));
                    iterator.value() = record;
                }
                changed.append(QJsonObject{{QStringLiteral("uuid"), iterator.key()},
                                           {QStringLiteral("alias"), record.value(QStringLiteral("alias"))}});
            }
        }
        aliases.insert(QStringLiteral("objects"), objects);
        summary.insert(QStringLiteral("changed"), changed);
        return;
    }

    if (action == QStringLiteral("pattern.base_point"))
    {
        const QString alias = RequiredString(arguments, QStringLiteral("alias"));
        VToolBasePointInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = alias;
        initData.x = UnitConvertor(arguments.value(QStringLiteral("x_mm")).toDouble(), Unit::Mm, Unit::Px);
        initData.y = UnitConvertor(arguments.value(QStringLiteral("y_mm")).toDouble(), Unit::Mm, Unit::Px);
        auto *tool = VToolBasePoint::Create(initData);
        RegisterObject(alias, QStringLiteral("BasePoint"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.line"))
    {
        VToolLineInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.firstPoint = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPoint = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        auto *tool = VToolLine::Create(initData);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Line"), tool->getId(),
                       aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.along_line"))
    {
        VToolAlongLineInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        initData.formula = arguments.contains(QStringLiteral("formula"))
                               ? RequiredString(arguments, QStringLiteral("formula"))
                               : NativeFormulaForMillimetres(arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        auto *tool = VToolAlongLine::Create(initData);
        RegisterObject(initData.name, QStringLiteral("AlongLine"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.midpoint"))
    {
        VToolAlongLineInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        initData.formula = currentLength + QStringLiteral("/2");
        auto *tool = VToolAlongLine::Create(initData);
        RegisterObject(initData.name, QStringLiteral("AlongLine"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.end_line"))
    {
        VToolEndLineInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.basePointId = ResolveObject(arguments.value(QStringLiteral("base_point")).toObject(), aliases);
        initData.formulaLength = arguments.contains(QStringLiteral("formula_length"))
                                     ? RequiredString(arguments, QStringLiteral("formula_length"))
                                     : NativeFormulaForMillimetres(
                                           arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.formulaAngle = arguments.contains(QStringLiteral("formula_angle"))
                                    ? RequiredString(arguments, QStringLiteral("formula_angle"))
                                    : QString::number(arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g',
                                                      15);
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        auto *tool = VToolEndLine::Create(initData);
        RegisterObject(initData.name, QStringLiteral("EndLine"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.line_intersect"))
    {
        VToolLineIntersectInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.p1Line1Id = ResolveObject(arguments.value(QStringLiteral("line1_p1")).toObject(), aliases);
        initData.p2Line1Id = ResolveObject(arguments.value(QStringLiteral("line1_p2")).toObject(), aliases);
        initData.p1Line2Id = ResolveObject(arguments.value(QStringLiteral("line2_p1")).toObject(), aliases);
        initData.p2Line2Id = ResolveObject(arguments.value(QStringLiteral("line2_p2")).toObject(), aliases);
        auto *tool = VToolLineIntersect::Create(initData);
        RegisterObject(initData.name, QStringLiteral("LineIntersect"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.arc"))
    {
        VToolArcInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.center = ResolveObject(arguments.value(QStringLiteral("center")).toObject(), aliases);
        initData.radius = arguments.contains(QStringLiteral("formula_radius"))
                              ? RequiredString(arguments, QStringLiteral("formula_radius"))
                              : NativeFormulaForMillimetres(arguments.value(QStringLiteral("radius_mm")).toDouble());
        initData.f1 = arguments.contains(QStringLiteral("formula_start_angle"))
                          ? RequiredString(arguments, QStringLiteral("formula_start_angle"))
                          : QString::number(arguments.value(QStringLiteral("start_angle_deg")).toDouble(), 'g', 15);
        initData.f2 = arguments.contains(QStringLiteral("formula_end_angle"))
                          ? RequiredString(arguments, QStringLiteral("formula_end_angle"))
                          : QString::number(arguments.value(QStringLiteral("end_angle_deg")).toDouble(), 'g', 15);
        initData.color = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        auto *tool = VToolArc::Create(initData);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Arc"), tool->getId(),
                       aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.spline"))
    {
        VToolSplineInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.point1 = ResolveObject(arguments.value(QStringLiteral("point1")).toObject(), aliases);
        initData.point4 = ResolveObject(arguments.value(QStringLiteral("point4")).toObject(), aliases);
        initData.a1 = arguments.contains(QStringLiteral("formula_angle1"))
                          ? RequiredString(arguments, QStringLiteral("formula_angle1"))
                          : QString::number(arguments.value(QStringLiteral("angle1_deg")).toDouble(), 'g', 15);
        initData.a2 = arguments.contains(QStringLiteral("formula_angle2"))
                          ? RequiredString(arguments, QStringLiteral("formula_angle2"))
                          : QString::number(arguments.value(QStringLiteral("angle2_deg")).toDouble(), 'g', 15);
        initData.l1 = arguments.contains(QStringLiteral("formula_length1"))
                          ? RequiredString(arguments, QStringLiteral("formula_length1"))
                          : NativeFormulaForMillimetres(arguments.value(QStringLiteral("length1_mm")).toDouble());
        initData.l2 = arguments.contains(QStringLiteral("formula_length2"))
                          ? RequiredString(arguments, QStringLiteral("formula_length2"))
                          : NativeFormulaForMillimetres(arguments.value(QStringLiteral("length2_mm")).toDouble());
        initData.color = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        auto *tool = VToolSpline::Create(initData);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Spline"), tool->getId(),
                       aliases, summary);
        return;
    }

    AddIssue(summary, QStringLiteral("error"), QStringLiteral("unsupported_action"),
             QStringLiteral("Native handler is not implemented: %1").arg(action));
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::ResolveObject(const QJsonObject &reference, const QJsonObject &aliases) const -> quint32
{
    const QString uuid = reference.value(QStringLiteral("uuid")).toString();
    const QString alias = reference.value(QStringLiteral("alias")).toString();
    const QJsonObject objects = aliases.value(QStringLiteral("objects")).toObject();
    QList<quint32> matches;
    for (auto iterator = objects.constBegin(); iterator != objects.constEnd(); ++iterator)
    {
        const QJsonObject record = iterator.value().toObject();
        if (record.value(QStringLiteral("deleted")).toBool())
        {
            continue;
        }
        if ((!uuid.isEmpty() && iterator.key() == uuid) || (!alias.isEmpty() && record.value(QStringLiteral("alias")) == alias))
        {
            matches.append(static_cast<quint32>(record.value(QStringLiteral("native_id")).toInteger()));
        }
    }
    if (matches.size() > 1)
    {
        throw std::invalid_argument(QStringLiteral("Alias is ambiguous: %1").arg(alias).toStdString());
    }
    if (matches.size() == 1)
    {
        return matches.constFirst();
    }

    if (!alias.isEmpty())
    {
        const auto *objectsById = m_window->pattern->CalculationGObjects();
        for (auto iterator = objectsById->constBegin(); iterator != objectsById->constEnd(); ++iterator)
        {
            if (iterator.value()->name() == alias)
            {
                matches.append(iterator.key());
            }
        }
    }
    if (matches.size() > 1)
    {
        throw std::invalid_argument(QStringLiteral("Object name is ambiguous: %1").arg(alias).toStdString());
    }
    if (matches.size() == 1)
    {
        return matches.constFirst();
    }
    throw std::invalid_argument(QStringLiteral("Unknown object reference: %1").arg(alias).toStdString());
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::RegisterObject(const QString &alias, const QString &kind, quint32 nativeId, QJsonObject &aliases,
                                     QJsonObject &summary) const -> void
{
    QJsonObject objects = aliases.value(QStringLiteral("objects")).toObject();
    for (auto iterator = objects.constBegin(); iterator != objects.constEnd(); ++iterator)
    {
        const QJsonObject record = iterator.value().toObject();
        if (!record.value(QStringLiteral("deleted")).toBool() && record.value(QStringLiteral("alias")) == alias)
        {
            throw std::invalid_argument(QStringLiteral("Alias already exists: %1").arg(alias).toStdString());
        }
    }

    const QString uuid = QUuid::createUuid().toString(QUuid::WithoutBraces);
    objects.insert(uuid, QJsonObject{{QStringLiteral("uuid"), uuid},
                                     {QStringLiteral("alias"), alias},
                                     {QStringLiteral("domain"), QStringLiteral("pattern")},
                                     {QStringLiteral("kind"), kind},
                                     {QStringLiteral("native_id"), static_cast<qint64>(nativeId)},
                                     {QStringLiteral("deleted"), false}});
    aliases.insert(QStringLiteral("objects"), objects);

    QJsonArray created = summary.value(QStringLiteral("created")).toArray();
    created.append(QJsonObject{{QStringLiteral("uuid"), uuid}, {QStringLiteral("alias"), alias}});
    summary.insert(QStringLiteral("created"), created);
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::CandidateRoot(const QString &projectRoot, const QString &changeSetId) -> QString
{
    return QDir(projectRoot).filePath(QStringLiteral(".garmentcad/changesets/%1").arg(changeSetId));
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::ValidateChangeSetId(const QString &changeSetId) -> void
{
    static const QRegularExpression safeId(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"));
    if (!safeId.match(changeSetId).hasMatch())
    {
        throw std::invalid_argument("Invalid change-set ID");
    }
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::ReadJsonFile(const QString &path) -> QJsonObject
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
    {
        throw std::runtime_error(QStringLiteral("Unable to read %1").arg(path).toStdString());
    }
    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !document.isObject())
    {
        throw std::runtime_error(QStringLiteral("Invalid JSON file %1: %2").arg(path, error.errorString()).toStdString());
    }
    return document.object();
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::WriteJsonFile(const QString &path, const QJsonObject &object) -> void
{
    QDir().mkpath(QFileInfo(path).absolutePath());
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly) || file.write(QJsonDocument(object).toJson(QJsonDocument::Indented)) < 0 ||
        !file.commit())
    {
        throw std::runtime_error(QStringLiteral("Unable to write %1").arg(path).toStdString());
    }
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::AtomicCopy(const QString &source, const QString &destination) -> void
{
    QFile input(source);
    if (!input.open(QIODevice::ReadOnly))
    {
        throw std::runtime_error(QStringLiteral("Unable to read candidate source %1").arg(source).toStdString());
    }
    QDir().mkpath(QFileInfo(destination).absolutePath());
    QSaveFile output(destination);
    if (!output.open(QIODevice::WriteOnly) || output.write(input.readAll()) < 0 || !output.commit())
    {
        throw std::runtime_error(QStringLiteral("Unable to install %1").arg(destination).toStdString());
    }
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::AddIssue(QJsonObject &summary, const QString &severity, const QString &code,
                               const QString &message) -> void
{
    QJsonArray issues = summary.value(QStringLiteral("issues")).toArray();
    issues.append(QJsonObject{{QStringLiteral("severity"), severity},
                              {QStringLiteral("code"), code},
                              {QStringLiteral("message"), message},
                              {QStringLiteral("objects"), QJsonArray{}},
                              {QStringLiteral("details"), QJsonObject{}}});
    summary.insert(QStringLiteral("issues"), issues);
}
