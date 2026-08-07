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
#include "../vtools/tools/drawTools/toolcurve/vtoolarcwithlength.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolabstractcurve.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolcubicbezier.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolcubicbezierpath.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolellipticalarc.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolellipticalarcwithlength.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolspline.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolsplinepath.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoollineintersect.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolpointfromarcandtangent.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolpointfromcircleandtangent.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolpointofcontact.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolpointofintersection.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolpointofintersectionarcs.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolpointofintersectioncircles.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolpointofintersectioncurves.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtooltriangle.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoolbisector.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoolcurveintersectaxis.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoolendline.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoolheight.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoollineintersectaxis.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoolnormal.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoolshoulderpoint.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toollinepoint/vtoolalongline.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toolcut/vtoolcutarc.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toolcut/vtoolcutspline.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/toolcut/vtoolcutsplinepath.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolbasepoint.h"
#include "../vtools/tools/drawTools/toolpoint/toolsinglepoint/vtoolsinglepoint.h"
#include "../vtools/tools/drawTools/vtoolline.h"
#include "../vtools/tools/vinteractivetool.h"
#include "../vgeometry/vcubicbezier.h"
#include "../vgeometry/vcubicbezierpath.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QSaveFile>
#include <QTextStream>
#include <QUuid>

#include <algorithm>
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

auto CrossPoint(const QJsonObject &arguments) -> CrossCirclesPoint
{
    const int solution = arguments.value(QStringLiteral("solution")).toInt(1);
    if (solution != 1 && solution != 2)
    {
        throw std::invalid_argument("solution must be 1 or 2");
    }
    return static_cast<CrossCirclesPoint>(solution);
}

auto VerticalCrossPoint(const QJsonObject &arguments) -> VCrossCurvesPoint
{
    const int solution = arguments.value(QStringLiteral("vertical_solution")).toInt(1);
    if (solution != 1 && solution != 2)
    {
        throw std::invalid_argument("vertical_solution must be 1 or 2");
    }
    return static_cast<VCrossCurvesPoint>(solution);
}

auto HorizontalCrossPoint(const QJsonObject &arguments) -> HCrossCurvesPoint
{
    const int solution = arguments.value(QStringLiteral("horizontal_solution")).toInt(1);
    if (solution != 1 && solution != 2)
    {
        throw std::invalid_argument("horizontal_solution must be 1 or 2");
    }
    return static_cast<HCrossCurvesPoint>(solution);
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
                            QStringLiteral("pattern.arc_start"), QStringLiteral("pattern.arc_end"),
                            QStringLiteral("pattern.arc_with_length"), QStringLiteral("pattern.elliptical_arc"),
                            QStringLiteral("pattern.elliptical_arc_with_length"),
                            QStringLiteral("pattern.spline"), QStringLiteral("pattern.spline_path"),
                            QStringLiteral("pattern.cubic_bezier"), QStringLiteral("pattern.cubic_bezier_path"),
                            QStringLiteral("pattern.formula_evaluate"),
                            QStringLiteral("pattern.dependency_query"), QStringLiteral("measurement.increment_set"),
                            QStringLiteral("measurement.increment_remove"),
                            QStringLiteral("measurement.final_measurement_set"),
                            QStringLiteral("pattern.shoulder_point"), QStringLiteral("pattern.normal"),
                            QStringLiteral("pattern.bisector"), QStringLiteral("pattern.height"),
                            QStringLiteral("pattern.triangle"), QStringLiteral("pattern.point_of_intersection"),
                            QStringLiteral("pattern.point_of_contact"),
                            QStringLiteral("pattern.point_of_intersection_circles"),
                            QStringLiteral("pattern.point_of_intersection_arcs"),
                            QStringLiteral("pattern.point_of_intersection_curves"),
                            QStringLiteral("pattern.point_from_circle_and_tangent"),
                            QStringLiteral("pattern.point_from_arc_and_tangent"),
                            QStringLiteral("pattern.line_intersect_axis"),
                            QStringLiteral("pattern.curve_intersect_axis"),
                            QStringLiteral("pattern.arc_intersect_axis"), QStringLiteral("pattern.cut_arc"),
                            QStringLiteral("pattern.cut_spline"), QStringLiteral("pattern.cut_spline_path")}}};
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

    if (action == QStringLiteral("pattern.formula_evaluate"))
    {
        QString formula = RequiredString(arguments, QStringLiteral("formula"));
        const qreal value = VAbstractTool::CheckFormula(NULL_ID, formula, m_window->pattern);
        QJsonObject measurements = summary.value(QStringLiteral("measurements")).toObject();
        if (arguments.value(QStringLiteral("quantity")).toString() == QStringLiteral("angle"))
        {
            measurements.insert(QStringLiteral("formula.value_deg"), value);
        }
        else
        {
            measurements.insert(QStringLiteral("formula.value_mm"),
                                UnitConvertor(value, VAbstractValApplication::VApp()->patternUnits(), Unit::Mm));
        }
        summary.insert(QStringLiteral("measurements"), measurements);
        return;
    }

    if (action == QStringLiteral("pattern.dependency_query"))
    {
        const quint32 nativeId = ResolveObject(operation.value(QStringLiteral("target")).toObject(), aliases);
        QJsonObject dependencies;
        const auto variableDependencies = m_window->pattern->DataDependencyVariables();
        for (auto iterator = variableDependencies.constBegin(); iterator != variableDependencies.constEnd(); ++iterator)
        {
            if (iterator.value().contains(nativeId))
            {
                QJsonArray dependents;
                for (quint32 id : iterator.value())
                {
                    dependents.append(static_cast<qint64>(id));
                }
                dependencies.insert(iterator.key(), dependents);
            }
        }
        QJsonArray issues = summary.value(QStringLiteral("issues")).toArray();
        issues.append(QJsonObject{{QStringLiteral("severity"), QStringLiteral("info")},
                                  {QStringLiteral("code"), QStringLiteral("dependency_query")},
                                  {QStringLiteral("message"),
                                   QStringLiteral("Formula dependencies for native object %1").arg(nativeId)},
                                  {QStringLiteral("objects"), QJsonArray{}},
                                  {QStringLiteral("details"), dependencies}});
        summary.insert(QStringLiteral("issues"), issues);
        return;
    }

    if (action == QStringLiteral("measurement.increment_set"))
    {
        const QString name = RequiredString(arguments, QStringLiteral("name"));
        if (!m_window->pattern->DataIncrements().contains(name))
        {
            m_window->doc->AddEmptyIncrement(name);
        }
        const QString formula = arguments.contains(QStringLiteral("formula"))
                                    ? RequiredString(arguments, QStringLiteral("formula"))
                                    : NativeFormulaForMillimetres(
                                          arguments.value(QStringLiteral("value_mm")).toDouble());
        m_window->doc->SetIncrementFormula(name, formula);
        m_window->doc->SetIncrementDescription(name, arguments.value(QStringLiteral("description")).toString());
        m_window->doc->SetIncrementSpecialUnits(name,
                                                arguments.value(QStringLiteral("special_units")).toBool(false));
        m_window->doc->LiteParseIncrements();
        QJsonObject measurements = summary.value(QStringLiteral("measurements")).toObject();
        QString evaluated = formula;
        const qreal value = VAbstractTool::CheckFormula(NULL_ID, evaluated, m_window->pattern);
        measurements.insert(name,
                            UnitConvertor(value, VAbstractValApplication::VApp()->patternUnits(), Unit::Mm));
        summary.insert(QStringLiteral("measurements"), measurements);
        return;
    }

    if (action == QStringLiteral("measurement.increment_remove"))
    {
        const QString name = RequiredString(arguments, QStringLiteral("name"));
        m_window->doc->RemoveIncrement(name);
        m_window->doc->LiteParseIncrements();
        return;
    }

    if (action == QStringLiteral("measurement.final_measurement_set"))
    {
        const QString name = RequiredString(arguments, QStringLiteral("name"));
        QVector<VFinalMeasurement> measurements = m_window->doc->GetFinalMeasurements();
        auto iterator = std::find_if(measurements.begin(), measurements.end(),
                                     [&name](const VFinalMeasurement &item) { return item.name == name; });
        const VFinalMeasurement replacement{name, RequiredString(arguments, QStringLiteral("formula")),
                                              arguments.value(QStringLiteral("description")).toString()};
        if (iterator == measurements.end())
        {
            measurements.append(replacement);
        }
        else
        {
            *iterator = replacement;
        }
        m_window->doc->SetFinalMeasurements(measurements);
        return;
    }

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

    if (action == QStringLiteral("pattern.arc") || action == QStringLiteral("pattern.arc_start") ||
        action == QStringLiteral("pattern.arc_end"))
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

    if (action == QStringLiteral("pattern.arc_with_length"))
    {
        VToolArcWithLengthInitData initData;
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
        initData.length = arguments.contains(QStringLiteral("formula_length"))
                              ? RequiredString(arguments, QStringLiteral("formula_length"))
                              : NativeFormulaForMillimetres(arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.color = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        auto *tool = VToolArcWithLength::Create(initData);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("ArcWithLength"),
                       tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.elliptical_arc") ||
        action == QStringLiteral("pattern.elliptical_arc_with_length"))
    {
        const auto radius1 = arguments.contains(QStringLiteral("formula_radius1"))
                                 ? RequiredString(arguments, QStringLiteral("formula_radius1"))
                                 : NativeFormulaForMillimetres(
                                       arguments.value(QStringLiteral("radius1_mm")).toDouble());
        const auto radius2 = arguments.contains(QStringLiteral("formula_radius2"))
                                 ? RequiredString(arguments, QStringLiteral("formula_radius2"))
                                 : NativeFormulaForMillimetres(
                                       arguments.value(QStringLiteral("radius2_mm")).toDouble());
        const auto startAngle = arguments.contains(QStringLiteral("formula_start_angle"))
                                    ? RequiredString(arguments, QStringLiteral("formula_start_angle"))
                                    : QString::number(
                                          arguments.value(QStringLiteral("start_angle_deg")).toDouble(), 'g', 15);
        const auto rotation = arguments.contains(QStringLiteral("formula_rotation_angle"))
                                  ? RequiredString(arguments, QStringLiteral("formula_rotation_angle"))
                                  : QString::number(
                                        arguments.value(QStringLiteral("rotation_angle_deg")).toDouble(), 'g', 15);
        if (action == QStringLiteral("pattern.elliptical_arc"))
        {
            VToolEllipticalArcInitData initData;
            initData.scene = m_window->m_sceneDraw;
            initData.doc = m_window->doc;
            initData.data = m_window->pattern;
            initData.parse = Document::FullParse;
            initData.typeCreation = Source::FromGui;
            initData.center = ResolveObject(arguments.value(QStringLiteral("center")).toObject(), aliases);
            initData.radius1 = radius1;
            initData.radius2 = radius2;
            initData.f1 = startAngle;
            initData.f2 = arguments.contains(QStringLiteral("formula_end_angle"))
                              ? RequiredString(arguments, QStringLiteral("formula_end_angle"))
                              : QString::number(
                                    arguments.value(QStringLiteral("end_angle_deg")).toDouble(), 'g', 15);
            initData.rotationAngle = rotation;
            initData.color = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
            initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
            initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
            auto *tool = VToolEllipticalArc::Create(initData);
            RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("EllipticalArc"),
                           tool->getId(), aliases, summary);
            return;
        }

        VToolEllipticalArcWithLengthInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.center = ResolveObject(arguments.value(QStringLiteral("center")).toObject(), aliases);
        initData.radius1 = radius1;
        initData.radius2 = radius2;
        initData.f1 = startAngle;
        initData.length = arguments.contains(QStringLiteral("formula_length"))
                              ? RequiredString(arguments, QStringLiteral("formula_length"))
                              : NativeFormulaForMillimetres(arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.rotationAngle = rotation;
        initData.color = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        auto *tool = VToolEllipticalArcWithLength::Create(initData);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")),
                       QStringLiteral("EllipticalArcWithLength"), tool->getId(), aliases, summary);
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

    if (action == QStringLiteral("pattern.cubic_bezier"))
    {
        const auto p1Id = ResolveObject(arguments.value(QStringLiteral("point1")).toObject(), aliases);
        const auto p2Id = ResolveObject(arguments.value(QStringLiteral("point2")).toObject(), aliases);
        const auto p3Id = ResolveObject(arguments.value(QStringLiteral("point3")).toObject(), aliases);
        const auto p4Id = ResolveObject(arguments.value(QStringLiteral("point4")).toObject(), aliases);
        auto p1 = m_window->pattern->GeometricObject<VPointF>(p1Id);
        auto p2 = m_window->pattern->GeometricObject<VPointF>(p2Id);
        auto p3 = m_window->pattern->GeometricObject<VPointF>(p3Id);
        auto p4 = m_window->pattern->GeometricObject<VPointF>(p4Id);

        VToolCubicBezierInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.spline = new VCubicBezier(*p1, *p2, *p3, *p4);
        initData.spline->SetColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        initData.spline->SetPenStyle(arguments.value(QStringLiteral("line_type")).toString(TypeLineLine));
        initData.spline->SetAliasSuffix(arguments.value(QStringLiteral("native_alias_suffix")).toString());
        auto *tool = VToolCubicBezier::Create(initData);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("CubicBezier"),
                       tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.spline_path"))
    {
        const QJsonArray pathPoints = arguments.value(QStringLiteral("points")).toArray();
        if (pathPoints.size() < 2)
        {
            throw std::invalid_argument("spline_path requires at least two points");
        }

        VToolSplinePathInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.color = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        for (const QJsonValue value : pathPoints)
        {
            const QJsonObject point = value.toObject();
            initData.points.append(ResolveObject(point.value(QStringLiteral("point")).toObject(), aliases));
            initData.a1.append(point.contains(QStringLiteral("formula_angle1"))
                                   ? RequiredString(point, QStringLiteral("formula_angle1"))
                                   : QString::number(
                                         point.value(QStringLiteral("angle1_deg")).toDouble(), 'g', 15));
            initData.a2.append(point.contains(QStringLiteral("formula_angle2"))
                                   ? RequiredString(point, QStringLiteral("formula_angle2"))
                                   : QString::number(
                                         point.value(QStringLiteral("angle2_deg")).toDouble(), 'g', 15));
            initData.l1.append(point.contains(QStringLiteral("formula_length1"))
                                   ? RequiredString(point, QStringLiteral("formula_length1"))
                                   : NativeFormulaForMillimetres(
                                         point.value(QStringLiteral("length1_mm")).toDouble()));
            initData.l2.append(point.contains(QStringLiteral("formula_length2"))
                                   ? RequiredString(point, QStringLiteral("formula_length2"))
                                   : NativeFormulaForMillimetres(
                                         point.value(QStringLiteral("length2_mm")).toDouble()));
        }
        auto *tool = VToolSplinePath::Create(initData);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("SplinePath"),
                       tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.cubic_bezier_path"))
    {
        const QJsonArray pointReferences = arguments.value(QStringLiteral("points")).toArray();
        if (pointReferences.size() < 4 || (pointReferences.size() - 1) % 3 != 0)
        {
            throw std::invalid_argument("cubic_bezier_path requires 3n+1 points");
        }
        QVector<VPointF> points;
        points.reserve(pointReferences.size());
        for (const QJsonValue value : pointReferences)
        {
            const auto pointId = ResolveObject(value.toObject(), aliases);
            points.append(*m_window->pattern->GeometricObject<VPointF>(pointId));
        }

        VToolCubicBezierPathInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.path = new VCubicBezierPath(points);
        initData.path->SetColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        initData.path->SetPenStyle(arguments.value(QStringLiteral("line_type")).toString(TypeLineLine));
        initData.path->SetAliasSuffix(arguments.value(QStringLiteral("native_alias_suffix")).toString());
        auto *tool = VToolCubicBezierPath::Create(initData);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("CubicBezierPath"),
                       tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.shoulder_point"))
    {
        VToolShoulderPointInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.p1Line = ResolveObject(arguments.value(QStringLiteral("line_p1")).toObject(), aliases);
        initData.p2Line = ResolveObject(arguments.value(QStringLiteral("line_p2")).toObject(), aliases);
        initData.pShoulder = ResolveObject(arguments.value(QStringLiteral("shoulder_point")).toObject(), aliases);
        initData.formula = arguments.contains(QStringLiteral("formula"))
                               ? RequiredString(arguments, QStringLiteral("formula"))
                               : NativeFormulaForMillimetres(
                                     arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        auto *tool = VToolShoulderPoint::Create(initData);
        RegisterObject(initData.name, QStringLiteral("ShoulderPoint"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.normal"))
    {
        VToolNormalInitData initData;
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
                               : NativeFormulaForMillimetres(
                                     arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.angle = arguments.value(QStringLiteral("angle_deg")).toDouble();
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        auto *tool = VToolNormal::Create(initData);
        RegisterObject(initData.name, QStringLiteral("Normal"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.bisector"))
    {
        VToolBisectorInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("vertex")).toObject(), aliases);
        initData.thirdPointId = ResolveObject(arguments.value(QStringLiteral("third_point")).toObject(), aliases);
        initData.formula = arguments.contains(QStringLiteral("formula"))
                               ? RequiredString(arguments, QStringLiteral("formula"))
                               : NativeFormulaForMillimetres(
                                     arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        auto *tool = VToolBisector::Create(initData);
        RegisterObject(initData.name, QStringLiteral("Bisector"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.height"))
    {
        VToolHeightInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.basePointId = ResolveObject(arguments.value(QStringLiteral("base_point")).toObject(), aliases);
        initData.p1LineId = ResolveObject(arguments.value(QStringLiteral("line_p1")).toObject(), aliases);
        initData.p2LineId = ResolveObject(arguments.value(QStringLiteral("line_p2")).toObject(), aliases);
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        auto *tool = VToolHeight::Create(initData);
        RegisterObject(initData.name, QStringLiteral("Height"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.triangle"))
    {
        VToolTriangleInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.axisP1Id = ResolveObject(arguments.value(QStringLiteral("axis_p1")).toObject(), aliases);
        initData.axisP2Id = ResolveObject(arguments.value(QStringLiteral("axis_p2")).toObject(), aliases);
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        auto *tool = VToolTriangle::Create(initData);
        RegisterObject(initData.name, QStringLiteral("Triangle"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.point_of_intersection"))
    {
        VToolPointOfIntersectionInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        auto *tool = VToolPointOfIntersection::Create(initData);
        RegisterObject(initData.name, QStringLiteral("PointOfIntersection"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.point_of_contact"))
    {
        VToolPointOfContactInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.center = ResolveObject(arguments.value(QStringLiteral("center")).toObject(), aliases);
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("line_p1")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("line_p2")).toObject(), aliases);
        initData.radius = arguments.contains(QStringLiteral("formula_radius"))
                              ? RequiredString(arguments, QStringLiteral("formula_radius"))
                              : NativeFormulaForMillimetres(arguments.value(QStringLiteral("radius_mm")).toDouble());
        auto *tool = VToolPointOfContact::Create(initData);
        RegisterObject(initData.name, QStringLiteral("PointOfContact"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.point_of_intersection_circles"))
    {
        VToolPointOfIntersectionCirclesInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.firstCircleCenterId =
            ResolveObject(arguments.value(QStringLiteral("first_center")).toObject(), aliases);
        initData.secondCircleCenterId =
            ResolveObject(arguments.value(QStringLiteral("second_center")).toObject(), aliases);
        initData.firstCircleRadius = arguments.contains(QStringLiteral("first_radius_formula"))
                                         ? RequiredString(arguments, QStringLiteral("first_radius_formula"))
                                         : NativeFormulaForMillimetres(
                                               arguments.value(QStringLiteral("first_radius_mm")).toDouble());
        initData.secondCircleRadius = arguments.contains(QStringLiteral("second_radius_formula"))
                                          ? RequiredString(arguments, QStringLiteral("second_radius_formula"))
                                          : NativeFormulaForMillimetres(
                                                arguments.value(QStringLiteral("second_radius_mm")).toDouble());
        initData.crossPoint = CrossPoint(arguments);
        auto *tool = VToolPointOfIntersectionCircles::Create(initData);
        RegisterObject(initData.name, QStringLiteral("PointOfIntersectionCircles"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.point_of_intersection_arcs"))
    {
        VToolPointOfIntersectionArcsInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.firstArcId = ResolveObject(arguments.value(QStringLiteral("first_arc")).toObject(), aliases);
        initData.secondArcId = ResolveObject(arguments.value(QStringLiteral("second_arc")).toObject(), aliases);
        initData.pType = CrossPoint(arguments);
        auto *tool = VToolPointOfIntersectionArcs::Create(initData);
        RegisterObject(initData.name, QStringLiteral("PointOfIntersectionArcs"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.point_of_intersection_curves"))
    {
        VToolPointOfIntersectionCurvesInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.firstCurveId = ResolveObject(arguments.value(QStringLiteral("first_curve")).toObject(), aliases);
        initData.secondCurveId =
            ResolveObject(arguments.value(QStringLiteral("second_curve")).toObject(), aliases);
        initData.vCrossPoint = VerticalCrossPoint(arguments);
        initData.hCrossPoint = HorizontalCrossPoint(arguments);
        auto *tool = VToolPointOfIntersectionCurves::Create(initData);
        RegisterObject(initData.name, QStringLiteral("PointOfIntersectionCurves"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.point_from_circle_and_tangent"))
    {
        VToolPointFromCircleAndTangentInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.circleCenterId = ResolveObject(arguments.value(QStringLiteral("center")).toObject(), aliases);
        initData.tangentPointId =
            ResolveObject(arguments.value(QStringLiteral("tangent_point")).toObject(), aliases);
        initData.circleRadius = arguments.contains(QStringLiteral("radius_formula"))
                                    ? RequiredString(arguments, QStringLiteral("radius_formula"))
                                    : NativeFormulaForMillimetres(
                                          arguments.value(QStringLiteral("radius_mm")).toDouble());
        initData.crossPoint = CrossPoint(arguments);
        auto *tool = VToolPointFromCircleAndTangent::Create(initData);
        RegisterObject(initData.name, QStringLiteral("PointFromCircleAndTangent"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.point_from_arc_and_tangent"))
    {
        VToolPointFromArcAndTangentInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.arcId = ResolveObject(arguments.value(QStringLiteral("arc")).toObject(), aliases);
        initData.tangentPointId =
            ResolveObject(arguments.value(QStringLiteral("tangent_point")).toObject(), aliases);
        initData.crossPoint = CrossPoint(arguments);
        auto *tool = VToolPointFromArcAndTangent::Create(initData);
        RegisterObject(initData.name, QStringLiteral("PointFromArcAndTangent"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.line_intersect_axis"))
    {
        VToolLineIntersectAxisInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.basePointId = ResolveObject(arguments.value(QStringLiteral("base_point")).toObject(), aliases);
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("line_p1")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("line_p2")).toObject(), aliases);
        initData.formulaAngle = arguments.contains(QStringLiteral("formula_angle"))
                                    ? RequiredString(arguments, QStringLiteral("formula_angle"))
                                    : QString::number(arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g', 15);
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        auto *tool = VToolLineIntersectAxis::Create(initData);
        RegisterObject(initData.name, QStringLiteral("LineIntersectAxis"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.curve_intersect_axis") ||
        action == QStringLiteral("pattern.arc_intersect_axis"))
    {
        VToolCurveIntersectAxisInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.basePointId = ResolveObject(arguments.value(QStringLiteral("base_point")).toObject(), aliases);
        initData.curveId = ResolveObject(arguments.value(QStringLiteral("curve")).toObject(), aliases);
        initData.formulaAngle = arguments.contains(QStringLiteral("formula_angle"))
                                    ? RequiredString(arguments, QStringLiteral("formula_angle"))
                                    : QString::number(arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g', 15);
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = arguments.value(QStringLiteral("line_color")).toString(ColorBlack);
        auto *tool = VToolCurveIntersectAxis::Create(initData);
        RegisterObject(initData.name, QStringLiteral("CurveIntersectAxis"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.cut_arc") || action == QStringLiteral("pattern.cut_spline") ||
        action == QStringLiteral("pattern.cut_spline_path"))
    {
        VToolCutInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name = RequiredString(arguments, QStringLiteral("alias"));
        initData.baseCurveId = ResolveObject(arguments.value(QStringLiteral("curve")).toObject(), aliases);
        initData.formula = arguments.contains(QStringLiteral("formula_length"))
                               ? RequiredString(arguments, QStringLiteral("formula_length"))
                               : NativeFormulaForMillimetres(
                                     arguments.value(QStringLiteral("length_mm")).toDouble());

        VToolSinglePoint *tool = nullptr;
        QString type;
        if (action == QStringLiteral("pattern.cut_arc"))
        {
            tool = VToolCutArc::Create(initData);
            type = QStringLiteral("CutArc");
        }
        else if (action == QStringLiteral("pattern.cut_spline"))
        {
            tool = VToolCutSpline::Create(initData);
            type = QStringLiteral("CutSpline");
        }
        else
        {
            tool = VToolCutSplinePath::Create(initData);
            type = QStringLiteral("CutSplinePath");
        }
        RegisterObject(initData.name, type, tool->getId(), aliases, summary);
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
