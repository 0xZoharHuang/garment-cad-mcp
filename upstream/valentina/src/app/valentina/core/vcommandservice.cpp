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
#include "../vmisc/qxtcsvmodel.h"
#include "../vtools/dialogs/tools/dialogalongline.h"
#include "../vtools/dialogs/tools/dialogendline.h"
#include "../vtools/dialogs/tools/dialogline.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolarc.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolarcwithlength.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolabstractcurve.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolcubicbezier.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolcubicbezierpath.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolellipticalarc.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolellipticalarcwithlength.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolgraduatedcurve.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolparallelcurve.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolspline.h"
#include "../vtools/tools/drawTools/toolcurve/vtoolsplinepath.h"
#include "../vtools/tools/drawTools/operation/flipping/vtoolflippingbyaxis.h"
#include "../vtools/tools/drawTools/operation/flipping/vtoolflippingbyline.h"
#include "../vtools/tools/drawTools/operation/vtoolmove.h"
#include "../vtools/tools/drawTools/operation/vtoolrotation.h"
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
#include "../vtools/tools/drawTools/toolpoint/tooldoublepoint/vtooltruedarts.h"
#include "../vtools/tools/drawTools/vtoolline.h"
#include "../vtools/tools/vinteractivetool.h"
#include "../vtools/tools/nodeDetails/vtoolpiecepath.h"
#include "../vtools/tools/nodeDetails/vtoolpin.h"
#include "../vtools/tools/nodeDetails/vtoolplacelabel.h"
#include "../vtools/tools/vtoolseamallowance.h"
#include "../vtools/tools/vtooluniondetails.h"
#include "../vtools/undocommands/undogroup.h"
#include "../vgeometry/vcubicbezier.h"
#include "../vgeometry/vcubicbezierpath.h"
#include "../vformat/vmeasurements.h"
#include "../ifc/xml/vpatternimage.h"
#include "../vpatterndb/vpiecenode.h"
#include "../vpatterndb/vpiecepath.h"
#include "../vpatterndb/variables/vmeasurement.h"
#include "../vlayout/vlayoutpoint.h"

#include <QDir>
#include <QDate>
#include <QCryptographicHash>
#include <QCoreApplication>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QImage>
#include <QPainter>
#include <QRegularExpression>
#include <QSaveFile>
#include <QProcess>
#include <QProcessEnvironment>
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

auto NativeObjectName(const QJsonObject &arguments, const QString &aliasField = QStringLiteral("alias"),
                      const QString &nativeField = QStringLiteral("native_name")) -> QString
{
    const QString alias = RequiredString(arguments, aliasField);
    const QString requested = arguments.value(nativeField).toString(alias);
    if (QRegularExpression(NameRegExp()).match(requested).hasMatch())
    {
        return requested;
    }

    QString sanitized = requested;
    sanitized.replace(QRegularExpression(QStringLiteral("[^\\p{L}\\p{N}_]")), QStringLiteral("_"));
    if (sanitized.isEmpty() || sanitized.at(0).isDigit())
    {
        sanitized.prepend(QStringLiteral("GC_"));
    }
    const QString digest = QString::fromLatin1(
        QCryptographicHash::hash(requested.toUtf8(), QCryptographicHash::Sha256).toHex().left(8));
    return sanitized + QLatin1Char('_') + digest;
}

auto PieceNodeTool(const QString &type) -> Tool
{
    if (type == QStringLiteral("point"))
    {
        return Tool::NodePoint;
    }
    if (type == QStringLiteral("arc"))
    {
        return Tool::NodeArc;
    }
    if (type == QStringLiteral("elliptical_arc"))
    {
        return Tool::NodeElArc;
    }
    if (type == QStringLiteral("spline"))
    {
        return Tool::NodeSpline;
    }
    if (type == QStringLiteral("spline_path"))
    {
        return Tool::NodeSplinePath;
    }
    throw std::invalid_argument(QStringLiteral("Unsupported piece node type: %1").arg(type).toStdString());
}

auto PiecePathKind(const QString &type) -> PiecePathType
{
    if (type == QStringLiteral("internal"))
    {
        return PiecePathType::InternalPath;
    }
    if (type == QStringLiteral("custom_seam_allowance"))
    {
        return PiecePathType::CustomSeamAllowance;
    }
    throw std::invalid_argument(QStringLiteral("Unsupported piece path type: %1").arg(type).toStdString());
}

auto PlaceLabelKind(const QString &type) -> PlaceLabelType
{
    static const QHash<QString, PlaceLabelType> types{{QStringLiteral("segment"), PlaceLabelType::Segment},
                                                      {QStringLiteral("rectangle"), PlaceLabelType::Rectangle},
                                                      {QStringLiteral("cross"), PlaceLabelType::Cross},
                                                      {QStringLiteral("t_shaped"), PlaceLabelType::Tshaped},
                                                      {QStringLiteral("double_tree"), PlaceLabelType::Doubletree},
                                                      {QStringLiteral("corner"), PlaceLabelType::Corner},
                                                      {QStringLiteral("triangle"), PlaceLabelType::Triangle},
                                                      {QStringLiteral("h_shaped"), PlaceLabelType::Hshaped},
                                                      {QStringLiteral("button"), PlaceLabelType::Button},
                                                      {QStringLiteral("circle"), PlaceLabelType::Circle}};
    if (!types.contains(type))
    {
        throw std::invalid_argument(QStringLiteral("Unsupported place-label type: %1").arg(type).toStdString());
    }
    return types.value(type);
}

void CopyDirectoryFiles(const QString &sourcePath, const QString &destinationPath)
{
    const QDir source(sourcePath);
    if (!source.exists())
    {
        return;
    }
    QDir().mkpath(destinationPath);
    const QFileInfoList entries = source.entryInfoList(QDir::Files | QDir::Dirs | QDir::NoDotAndDotDot);
    for (const QFileInfo &entry : entries)
    {
        const QString destination = QDir(destinationPath).filePath(entry.fileName());
        if (entry.isDir())
        {
            CopyDirectoryFiles(entry.absoluteFilePath(), destination);
        }
        else
        {
            QFile::remove(destination);
            if (!QFile::copy(entry.absoluteFilePath(), destination))
            {
                throw std::runtime_error(
                    QStringLiteral("Unable to copy %1 to %2").arg(entry.absoluteFilePath(), destination).toStdString());
            }
        }
    }
}

auto CsvCell(QString value) -> QString
{
    value.replace(QLatin1Char('"'), QStringLiteral("\"\""));
    return QLatin1Char('"') + value + QLatin1Char('"');
}

void RenderThumbnail(QGraphicsScene *scene, const QString &path)
{
    QImage image(QSize(512, 512), QImage::Format_ARGB32_Premultiplied);
    image.fill(Qt::white);
    if (scene != nullptr)
    {
        QRectF source = scene->itemsBoundingRect();
        if (!source.isEmpty())
        {
            const qreal padding = qMax(source.width(), source.height()) * 0.04;
            source.adjust(-padding, -padding, padding, padding);
            QPainter painter(&image);
            painter.setRenderHint(QPainter::Antialiasing, true);
            scene->render(&painter, QRectF(8, 8, 496, 496), source, Qt::KeepAspectRatio);
        }
    }
    QDir().mkpath(QFileInfo(path).absolutePath());
    if (!image.save(path, "PNG"))
    {
        throw std::runtime_error("Unable to save Valentina preview thumbnail");
    }
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
    catch (const VException &error)
    {
        response = {{QStringLiteral("ok"), false},
                    {QStringLiteral("error"),
                     QJsonObject{{QStringLiteral("code"), QStringLiteral("valentina_error")},
                                 {QStringLiteral("message"), error.ErrorMessage()},
                                 {QStringLiteral("details"), error.DetailedInformation()}}}};
        exitCode = 1;
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
                {QStringLiteral("construction_adapters"),
                 QJsonArray{QStringLiteral("native_command"), QStringLiteral("gui_dialog")}},
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
                            QStringLiteral("measurement.file_create"), QStringLiteral("measurement.file_open"),
                            QStringLiteral("measurement.file_save"), QStringLiteral("measurement.set"),
                            QStringLiteral("measurement.rename"), QStringLiteral("measurement.remove"),
                            QStringLiteral("measurement.dimension_set"),
                            QStringLiteral("measurement.file_metadata_set"),
                            QStringLiteral("measurement.dimension_labels_set"),
                            QStringLiteral("measurement.restriction_set"),
                            QStringLiteral("measurement.restriction_remove"),
                            QStringLiteral("measurement.correction_set"),
                            QStringLiteral("measurement.value_alias_set"),
                            QStringLiteral("measurement.image_set"),
                            QStringLiteral("measurement.image_remove"),
                            QStringLiteral("measurement.import_csv"),
                            QStringLiteral("measurement.export_csv"), QStringLiteral("export.pattern"),
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
                            QStringLiteral("pattern.cut_spline"), QStringLiteral("pattern.cut_spline_path"),
                            QStringLiteral("pattern.parallel_curve"),
                            QStringLiteral("pattern.graduated_curve"), QStringLiteral("pattern.true_darts"),
                            QStringLiteral("pattern.move"), QStringLiteral("pattern.rotation"),
                            QStringLiteral("pattern.flipping_by_line"),
                            QStringLiteral("pattern.flipping_by_axis"), QStringLiteral("pattern.piece"),
                            QStringLiteral("pattern.piece_path"), QStringLiteral("pattern.pin"),
                            QStringLiteral("pattern.place_label"), QStringLiteral("pattern.insert_node"),
                            QStringLiteral("pattern.duplicate_detail"),
                            QStringLiteral("pattern.object_duplicate"), QStringLiteral("pattern.group"),
                            QStringLiteral("pattern.union_details"), QStringLiteral("pattern.snapshot")}}};
    }
    if (method == QStringLiteral("commands.preview"))
    {
        return Preview(request);
    }
    if (method == QStringLiteral("commands.commit"))
    {
        return Commit(request);
    }
    if (method == QStringLiteral("pattern.snapshot"))
    {
        return Snapshot(request);
    }
    throw std::invalid_argument(QStringLiteral("Unknown method: %1").arg(method).toStdString());
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::Snapshot(const QJsonObject &request) -> QJsonObject
{
    const QString projectRoot = QDir::cleanPath(RequiredString(request, QStringLiteral("project_root")));
    const QString patternPath = QDir(projectRoot).filePath(QStringLiteral("pattern/main.val"));
    if (!QFileInfo::exists(patternPath))
    {
        throw std::invalid_argument("The project does not contain pattern/main.val");
    }
    if (!m_window->LoadPattern(patternPath))
    {
        throw std::runtime_error("Valentina could not open pattern/main.val for snapshot");
    }

    const QJsonObject aliases =
        ReadJsonFile(QDir(projectRoot).filePath(QStringLiteral(".garmentcad/aliases.json")));
    const QJsonObject aliasObjects = aliases.value(QStringLiteral("objects")).toObject();
    const QJsonObject manifest = ReadJsonFile(QDir(projectRoot).filePath(QStringLiteral("garment.json")));
    const QUuid edgeNamespace(QStringLiteral("4eec45ae-b00d-5a3d-8cf5-98d9a8ec20a4"));
    QJsonArray pieces;

    const auto *dataPieces = m_window->pattern->DataPieces();
    QList<quint32> pieceIds = dataPieces->keys();
    std::sort(pieceIds.begin(), pieceIds.end());
    for (const quint32 nativeId : pieceIds)
    {
        const VPiece &piece = dataPieces->value(nativeId);
        QString pieceUuid;
        QString pieceAlias;
        for (auto aliasIterator = aliasObjects.constBegin(); aliasIterator != aliasObjects.constEnd(); ++aliasIterator)
        {
            const QJsonObject record = aliasIterator.value().toObject();
            if (!record.value(QStringLiteral("deleted")).toBool()
                && record.value(QStringLiteral("kind")).toString().compare(QStringLiteral("Piece"),
                                                                            Qt::CaseInsensitive) == 0
                && static_cast<quint32>(record.value(QStringLiteral("native_id")).toInteger()) == nativeId)
            {
                pieceUuid = aliasIterator.key();
                pieceAlias = record.value(QStringLiteral("alias")).toString();
                break;
            }
        }
        if (pieceAlias.isEmpty())
        {
            pieceAlias = piece.GetName();
        }
        if (pieceAlias.isEmpty())
        {
            pieceAlias = QStringLiteral("piece_%1").arg(nativeId);
        }
        if (pieceUuid.isEmpty())
        {
            // Older/external .val files may receive a fresh VPiece UUID on every load. Derive the public identity
            // from project identity plus the stable native piece id instead; once an alias record exists its UUID
            // above remains authoritative.
            pieceUuid = QUuid::createUuidV5(
                            edgeNamespace,
                            QStringLiteral("piece:%1:%2:%3")
                                .arg(manifest.value(QStringLiteral("project_id")).toString())
                                .arg(nativeId)
                                .arg(pieceAlias))
                            .toString(QUuid::WithoutBraces);
        }

        QVector<VLayoutPoint> points = piece.FullMainPathPoints(m_window->pattern);
        while (points.size() > 1
               && QLineF(points.constFirst(), points.constLast()).length() <= ToPixel(0.001, Unit::Mm))
        {
            points.removeLast();
        }
        if (points.size() < 3)
        {
            throw std::runtime_error(
                QStringLiteral("Piece %1 has fewer than three snapshot points").arg(pieceAlias).toStdString());
        }

        QJsonArray contour;
        for (qsizetype index = 0; index < points.size(); ++index)
        {
            const QString edgeAlias = QStringLiteral("%1.edge.%2").arg(pieceAlias).arg(index, 4, 10, QLatin1Char('0'));
            const QString edgeUuid =
                QUuid::createUuidV5(edgeNamespace, QStringLiteral("%1:%2").arg(pieceUuid).arg(index))
                    .toString(QUuid::WithoutBraces);
            contour.append(QJsonObject{{QStringLiteral("x_mm"), FromPixel(points.at(index).x(), Unit::Mm)},
                                       {QStringLiteral("y_mm"), FromPixel(points.at(index).y(), Unit::Mm)},
                                       {QStringLiteral("edge_uuid"), edgeUuid},
                                       {QStringLiteral("edge_alias"), edgeAlias},
                                       {QStringLiteral("curve_point"), points.at(index).CurvePoint()},
                                       {QStringLiteral("turn_point"), points.at(index).TurnPoint()}});
        }

        const qreal seamAllowanceMm =
            UnitConvertor(piece.GetSAWidth(), *m_window->pattern->GetPatternUnit(), Unit::Mm);
        pieces.append(QJsonObject{{QStringLiteral("uuid"), pieceUuid},
                                  {QStringLiteral("alias"), pieceAlias},
                                  {QStringLiteral("native_id"), static_cast<qint64>(nativeId)},
                                  {QStringLiteral("name"), piece.GetName()},
                                  {QStringLiteral("contour"), contour},
                                  {QStringLiteral("seam_allowance"), piece.IsSeamAllowance()},
                                  {QStringLiteral("seam_allowance_mm"), seamAllowanceMm}});
    }

    return {{QStringLiteral("schema_version"), QStringLiteral("1.0")},
            {QStringLiteral("units"), QStringLiteral("mm")},
            {QStringLiteral("revision"), manifest.value(QStringLiteral("current_revision")).toInteger()},
            {QStringLiteral("pieces"), pieces}};
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::Preview(const QJsonObject &request) -> QJsonObject
{
    const QString projectRoot = QDir::cleanPath(RequiredString(request, QStringLiteral("project_root")));
    const QString changeSetId = RequiredString(request, QStringLiteral("change_set_id"));
    ValidateChangeSetId(changeSetId);

    m_constructionAdapter = request.value(QStringLiteral("construction_adapter"))
                                .toString(QStringLiteral("native_command"));
    if (m_constructionAdapter != QStringLiteral("native_command") &&
        m_constructionAdapter != QStringLiteral("gui_dialog"))
    {
        throw std::invalid_argument("construction_adapter must be native_command or gui_dialog");
    }

    const QString sourcePattern = QDir(projectRoot).filePath(QStringLiteral("pattern/main.val"));
    if (!QFileInfo::exists(sourcePattern))
    {
        throw std::invalid_argument("The project does not contain pattern/main.val");
    }

    const QString candidateRoot = CandidateRoot(projectRoot, changeSetId);
    const QString candidatePattern = QDir(candidateRoot).filePath(QStringLiteral("pattern/main.val"));
    QDir().mkpath(QFileInfo(candidatePattern).absolutePath());
    CopyDirectoryFiles(QDir(projectRoot).filePath(QStringLiteral("pattern")),
                       QDir(candidateRoot).filePath(QStringLiteral("pattern")));
    CopyDirectoryFiles(QDir(projectRoot).filePath(QStringLiteral("measurements")),
                       QDir(candidateRoot).filePath(QStringLiteral("measurements")));
    m_candidateRoot = candidateRoot;
    m_candidatePattern = candidatePattern;

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
    RenderThumbnail(m_window->m_sceneDraw, QDir(candidateRoot).filePath(QStringLiteral("thumbnail.png")));

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
    CopyDirectoryFiles(QDir(candidateRoot).filePath(QStringLiteral("measurements")),
                       QDir(projectRoot).filePath(QStringLiteral("measurements")));
    return {{QStringLiteral("change_set_id"), changeSetId}};
}

//---------------------------------------------------------------------------------------------------------------------
auto VCommandService::ApplyOperation(const QJsonObject &operation, QJsonObject &aliases, QJsonObject &summary) -> void
{
    const QString action = RequiredString(operation, QStringLiteral("action"));
    const QJsonObject arguments = operation.value(QStringLiteral("arguments")).toObject();
    const auto measurementPath = [this](const QJsonObject &args) -> QString {
        QString path;
        if (args.contains(QStringLiteral("path")))
        {
            path = QDir(m_candidateRoot).filePath(RequiredString(args, QStringLiteral("path")));
        }
        else
        {
            const QString attached = m_window->doc->MPath();
            if (attached.isEmpty())
            {
                throw std::invalid_argument("No measurement file is attached; pass path or call measurement.file_open");
            }
            path = QDir(QFileInfo(m_candidatePattern).absolutePath()).filePath(attached);
        }
        path = QDir::cleanPath(QFileInfo(path).absoluteFilePath());
        const QString allowedRoot = QDir::cleanPath(QFileInfo(m_candidateRoot).absoluteFilePath()) + QLatin1Char('/');
        if (!path.startsWith(allowedRoot))
        {
            throw std::invalid_argument("Measurement path must stay inside the preview project");
        }
        return path;
    };
    const auto attachMeasurement = [this](const QString &path) {
        const QString relative = QDir(QFileInfo(m_candidatePattern).absolutePath()).relativeFilePath(path);
        m_window->doc->SetMPath(relative);
    };
    const auto reloadMeasurement = [this](const QString &path) {
        QString nativePath = path;
        if (!m_window->LoadMeasurements(m_candidatePattern, nativePath))
        {
            throw std::runtime_error("Valentina could not load the staged measurement file");
        }
        m_window->doc->LiteParseTree(Document::FullLiteParse);
    };
    const auto operationSources = [this, &aliases](const QJsonArray &items) -> QVector<SourceItem> {
        if (items.isEmpty())
        {
            throw std::invalid_argument("operation requires at least one source object");
        }
        QVector<SourceItem> source;
        source.reserve(items.size());
        for (const QJsonValue value : items)
        {
            const QJsonObject item = value.toObject();
            SourceItem sourceItem;
            sourceItem.id = ResolveObject(item.value(QStringLiteral("source")).toObject(), aliases);
            sourceItem.name = NativeObjectName(item);
            sourceItem.penStyle = item.value(QStringLiteral("line_type")).toString(TypeLineDefault);
            sourceItem.color = CanonicalToolColor(item.value(QStringLiteral("line_color")).toString(ColorDefault));
            source.append(sourceItem);
        }
        return source;
    };
    const auto registerDestinations = [this, &aliases, &summary](const QJsonArray &items,
                                                                 const QVector<DestinationItem> &destinations,
                                                                 const QString &kind) {
        if (items.size() != destinations.size())
        {
            throw std::runtime_error("native operation destination count mismatch");
        }
        for (qsizetype index = 0; index < items.size(); ++index)
        {
            RegisterObject(RequiredString(items.at(index).toObject(), QStringLiteral("alias")), kind,
                           destinations.at(index).id, aliases, summary);
        }
    };

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

    if (action == QStringLiteral("export.pattern"))
    {
        const QString format = arguments.value(QStringLiteral("format")).toString(QStringLiteral("pdf")).toLower();
        const QMap<QString, QPair<int, QString>> formats{
            {QStringLiteral("svg"), {0, QStringLiteral(".svg")}},
            {QStringLiteral("pdf"), {1, QStringLiteral(".pdf")}},
            {QStringLiteral("png"), {2, QStringLiteral(".png")}},
            {QStringLiteral("obj"), {3, QStringLiteral(".obj")}},
            {QStringLiteral("ps"), {4, QStringLiteral(".ps")}},
            {QStringLiteral("eps"), {5, QStringLiteral(".eps")}},
            {QStringLiteral("dxf_r10"), {6, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_ac1006"), {6, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf"), {7, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_r12"), {7, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_ac1009"), {7, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_r13"), {8, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_ac1012"), {8, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_r14"), {9, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_ac1014"), {9, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_2000"), {10, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_ac1015"), {10, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_2004"), {11, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_ac1018"), {11, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_2007"), {12, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_ac1021"), {12, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_2010"), {13, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_ac1024"), {13, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_2013"), {14, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_ac1027"), {14, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_aama"), {16, QStringLiteral(".dxf")}},
            {QStringLiteral("aama"), {16, QStringLiteral(".dxf")}},
            {QStringLiteral("dxf_astm"), {25, QStringLiteral(".dxf")}},
            {QStringLiteral("astm"), {25, QStringLiteral(".dxf")}},
            {QStringLiteral("pdf_tiled"), {33, QStringLiteral(".pdf")}},
            {QStringLiteral("rld"), {35, QStringLiteral(".rld")}},
            {QStringLiteral("tif"), {36, QStringLiteral(".tif")}},
            {QStringLiteral("hpgl"), {37, QStringLiteral(".hpgl")}},
            {QStringLiteral("hpgl2"), {38, QStringLiteral(".hpgl")}},
            {QStringLiteral("plt"), {39, QStringLiteral(".plt")}},
            {QStringLiteral("hpgl2_plt"), {40, QStringLiteral(".plt")}},
        };
        if (!formats.contains(format))
        {
            throw std::invalid_argument("Unsupported pattern export format");
        }
        const QPair<int, QString> nativeFormat = formats.value(format);
        const QString relative = arguments.value(QStringLiteral("output_path")).toString(
            QStringLiteral("artifacts/exports/pattern%1").arg(nativeFormat.second));
        const QString output = QFileInfo(QDir(m_candidateRoot).filePath(relative)).absoluteFilePath();
        const QString allowed = QFileInfo(m_candidateRoot).absoluteFilePath() + QLatin1Char('/');
        if (!output.startsWith(allowed))
        {
            throw std::invalid_argument("Pattern export path must stay inside the preview project");
        }
        QString baseName = QFileInfo(output).fileName();
        if (baseName.endsWith(nativeFormat.second, Qt::CaseInsensitive))
        {
            baseName.chop(nativeFormat.second.size());
        }
        if (baseName.isEmpty())
        {
            throw std::invalid_argument("Pattern export filename is empty");
        }
        const QString destination = QFileInfo(output).absolutePath();
        QDir().mkpath(destination);

        QStringList commandArguments{QStringLiteral("--basename"), baseName,
                                     QStringLiteral("--destination"), destination,
                                     QStringLiteral("--format"), QString::number(nativeFormat.first)};
        if (arguments.value(QStringLiteral("details_only")).toBool(true))
        {
            commandArguments.append(QStringLiteral("--exportOnlyDetails"));
        }
        if (arguments.value(QStringLiteral("binary_dxf")).toBool(false))
        {
            commandArguments.append(QStringLiteral("--bdxf"));
        }
        if (!arguments.value(QStringLiteral("show_grainline")).toBool(true))
        {
            commandArguments.append(QStringLiteral("--noGrainline"));
        }
        if (arguments.value(QStringLiteral("text_as_paths")).toBool(false))
        {
            commandArguments.append(QStringLiteral("--text2paths"));
        }
        QString saveError;
        if (!m_window->SavePattern(m_candidatePattern, saveError))
        {
            throw std::runtime_error(
                QStringLiteral("Unable to save pattern before export: %1").arg(saveError).toStdString());
        }
        const QString exportSourceRoot =
            QDir(m_candidateRoot).filePath(QStringLiteral(".export-source/%1").arg(QUuid::createUuid().toString(
                QUuid::WithoutBraces)));
        const QString exportPattern = QDir(exportSourceRoot).filePath(QStringLiteral("pattern/main.val"));
        AtomicCopy(m_candidatePattern, exportPattern);
        const QString measurement = m_window->doc->MPath();
        if (!measurement.isEmpty())
        {
            const QString sourceMeasurement =
                QFileInfo(QDir(QFileInfo(m_candidatePattern).absolutePath()).filePath(measurement)).absoluteFilePath();
            const QString allowedRoot = QFileInfo(m_candidateRoot).absoluteFilePath() + QLatin1Char('/');
            if (!sourceMeasurement.startsWith(allowedRoot) || !QFileInfo::exists(sourceMeasurement))
            {
                throw std::runtime_error("Pattern measurement file is missing from the preview project");
            }
            AtomicCopy(sourceMeasurement,
                       QDir(QFileInfo(exportPattern).absolutePath()).filePath(measurement));
        }
        commandArguments.append(exportPattern);

        QProcess process;
        QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
        environment.remove(QStringLiteral("GARMENTCAD_COMMAND_MODE"));
        environment.insert(QStringLiteral("QT_QPA_PLATFORM"), QStringLiteral("offscreen"));
        process.setProcessEnvironment(environment);
        process.setProcessChannelMode(QProcess::MergedChannels);
        process.start(QCoreApplication::applicationFilePath(), commandArguments);
        const int timeout = qBound(5000, arguments.value(QStringLiteral("timeout_ms")).toInt(60000), 3600000);
        if (!process.waitForFinished(timeout))
        {
            process.kill();
            process.waitForFinished();
            throw std::runtime_error("Pattern export timed out");
        }
        if (process.exitStatus() != QProcess::NormalExit || process.exitCode() != 0)
        {
            throw std::runtime_error(
                QStringLiteral("Pattern export failed: %1").arg(QString::fromUtf8(process.readAll())).toStdString());
        }
        const QString expected = QDir(destination).filePath(baseName + nativeFormat.second);
        if (!QFileInfo::exists(expected) || QFileInfo(expected).size() == 0)
        {
            throw std::runtime_error("Valentina did not produce the expected pattern export");
        }
        QDir(exportSourceRoot).removeRecursively();
        QJsonArray created = summary.value(QStringLiteral("created")).toArray();
        created.append(QJsonObject{{QStringLiteral("alias"), relative}});
        summary.insert(QStringLiteral("created"), created);
        return;
    }

    if (action == QStringLiteral("measurement.file_create"))
    {
        const QString type = arguments.value(QStringLiteral("type")).toString(QStringLiteral("individual"));
        QString relativePath = arguments.value(QStringLiteral("path")).toString();
        if (relativePath.isEmpty())
        {
            relativePath = type == QStringLiteral("multisize") ? QStringLiteral("measurements/main.vst")
                                                                : QStringLiteral("measurements/main.vit");
        }
        QJsonObject pathArguments = arguments;
        pathArguments.insert(QStringLiteral("path"), relativePath);
        const QString path = measurementPath(pathArguments);
        QDir().mkpath(QFileInfo(path).absolutePath());

        Unit unit = Unit::Mm;
        VContainer data(VAbstractApplication::VApp()->TrVars(), &unit, VContainer::UniqueNamespace());
        std::unique_ptr<VMeasurements> measurements;
        if (type == QStringLiteral("individual"))
        {
            measurements = std::make_unique<VMeasurements>(unit, &data);
        }
        else if (type == QStringLiteral("multisize"))
        {
            QVector<MeasurementDimension_p> dimensions;
            for (const QJsonValue value : arguments.value(QStringLiteral("dimensions")).toArray())
            {
                const QJsonObject item = value.toObject();
                const QString axis = RequiredString(item, QStringLiteral("axis")).toUpper();
                const qreal minimum = item.value(QStringLiteral("min_mm")).toDouble();
                const qreal maximum = item.value(QStringLiteral("max_mm")).toDouble();
                const qreal step = item.value(QStringLiteral("step_mm")).toDouble();
                MeasurementDimension_p dimension;
                if (axis == QStringLiteral("X"))
                {
                    dimension = QSharedPointer<VXMeasurementDimension>::create(unit, minimum, maximum, step);
                }
                else if (axis == QStringLiteral("Y"))
                {
                    dimension = QSharedPointer<VYMeasurementDimension>::create(unit, minimum, maximum, step);
                }
                else if (axis == QStringLiteral("W"))
                {
                    dimension = QSharedPointer<VWMeasurementDimension>::create(unit, minimum, maximum, step);
                }
                else if (axis == QStringLiteral("Z"))
                {
                    dimension = QSharedPointer<VZMeasurementDimension>::create(unit, minimum, maximum, step);
                }
                else
                {
                    throw std::invalid_argument("Measurement dimension axis must be X, Y, W, or Z");
                }
                dimension->SetBaseValue(item.value(QStringLiteral("base_mm")).toDouble(minimum));
                dimension->SetBodyMeasurement(item.value(QStringLiteral("body_measurement")).toBool(true));
                dimension->SetCustomName(item.value(QStringLiteral("name")).toString());
                if (!dimension->IsValid())
                {
                    throw std::invalid_argument(
                        QStringLiteral("Invalid %1 dimension: %2").arg(axis, dimension->Error()).toStdString());
                }
                dimensions.append(dimension);
            }
            if (dimensions.isEmpty() || dimensions.size() > 3)
            {
                throw std::invalid_argument("Multisize files require one to three dimensions");
            }
            measurements = std::make_unique<VMeasurements>(unit, dimensions, &data);
            measurements->SetFullCircumference(arguments.value(QStringLiteral("full_circumference")).toBool(false));
        }
        else
        {
            throw std::invalid_argument("Measurement file type must be individual or multisize");
        }
        QString error;
        if (!measurements->SaveDocument(path, error))
        {
            throw std::runtime_error(QStringLiteral("Unable to create measurement file: %1").arg(error).toStdString());
        }
        attachMeasurement(path);
        reloadMeasurement(path);
        QJsonObject values = summary.value(QStringLiteral("measurements")).toObject();
        values.insert(QStringLiteral("file.created"), 1);
        summary.insert(QStringLiteral("measurements"), values);
        return;
    }

    if (action == QStringLiteral("measurement.file_open"))
    {
        const QString source = QDir::cleanPath(QFileInfo(
            RequiredString(arguments, QStringLiteral("source_path"))).absoluteFilePath());
        if (!QFileInfo::exists(source))
        {
            throw std::invalid_argument("Measurement source file does not exist");
        }
        QString relativePath = arguments.value(QStringLiteral("path")).toString();
        if (relativePath.isEmpty())
        {
            relativePath = QStringLiteral("measurements/%1").arg(QFileInfo(source).fileName());
        }
        QJsonObject pathArguments;
        pathArguments.insert(QStringLiteral("path"), relativePath);
        const QString destination = measurementPath(pathArguments);
        QDir().mkpath(QFileInfo(destination).absolutePath());
        Unit unit = Unit::Mm;
        VContainer data(VAbstractApplication::VApp()->TrVars(), &unit, VContainer::UniqueNamespace());
        VMeasurements measurements(&data);
        measurements.setXMLContent(source);
        QString error;
        if (!measurements.SaveDocument(destination, error))
        {
            throw std::runtime_error(QStringLiteral("Unable to import measurement file: %1").arg(error).toStdString());
        }
        attachMeasurement(destination);
        reloadMeasurement(destination);
        QJsonObject values = summary.value(QStringLiteral("measurements")).toObject();
        values.insert(QStringLiteral("file.opened"), 1);
        summary.insert(QStringLiteral("measurements"), values);
        return;
    }

    if (action == QStringLiteral("measurement.file_save") || action == QStringLiteral("measurement.set") ||
        action == QStringLiteral("measurement.rename") || action == QStringLiteral("measurement.remove") ||
        action == QStringLiteral("measurement.dimension_set") ||
        action == QStringLiteral("measurement.file_metadata_set") ||
        action == QStringLiteral("measurement.dimension_labels_set") ||
        action == QStringLiteral("measurement.restriction_set") ||
        action == QStringLiteral("measurement.restriction_remove") ||
        action == QStringLiteral("measurement.correction_set") ||
        action == QStringLiteral("measurement.value_alias_set") || action == QStringLiteral("measurement.image_set") ||
        action == QStringLiteral("measurement.image_remove") || action == QStringLiteral("measurement.import_csv"))
    {
        const QString path = measurementPath(arguments);
        if (!QFileInfo::exists(path))
        {
            throw std::invalid_argument("Attached measurement file does not exist in the project");
        }
        Unit unit = Unit::Mm;
        VContainer data(VAbstractApplication::VApp()->TrVars(), &unit, VContainer::UniqueNamespace());
        VMeasurements measurements(&data);
        measurements.setXMLContent(path);

        if (action == QStringLiteral("measurement.set"))
        {
            const QString name = RequiredString(arguments, QStringLiteral("name"));
            if (!measurements.ListAll().contains(name))
            {
                measurements.AddEmpty(name);
            }
            const qreal value = UnitConvertor(arguments.value(QStringLiteral("value_mm")).toDouble(), Unit::Mm,
                                              measurements.Units());
            if (measurements.Type() == MeasurementsType::Individual)
            {
                measurements.SetMValue(
                    name, arguments.value(QStringLiteral("formula")).toString(QString::number(value, 'g', 15)));
            }
            else
            {
                measurements.SetMBaseValue(name, value);
                if (arguments.contains(QStringLiteral("shift_a_mm")))
                {
                    measurements.SetMShiftA(
                        name, UnitConvertor(arguments.value(QStringLiteral("shift_a_mm")).toDouble(), Unit::Mm,
                                            measurements.Units()));
                }
                if (arguments.contains(QStringLiteral("shift_b_mm")))
                {
                    measurements.SetMShiftB(
                        name, UnitConvertor(arguments.value(QStringLiteral("shift_b_mm")).toDouble(), Unit::Mm,
                                            measurements.Units()));
                }
                if (arguments.contains(QStringLiteral("shift_c_mm")))
                {
                    measurements.SetMShiftC(
                        name, UnitConvertor(arguments.value(QStringLiteral("shift_c_mm")).toDouble(), Unit::Mm,
                                            measurements.Units()));
                }
            }
            if (arguments.contains(QStringLiteral("description")))
            {
                measurements.SetMDescription(name, arguments.value(QStringLiteral("description")).toString());
            }
            if (arguments.contains(QStringLiteral("full_name")))
            {
                measurements.SetMFullName(name, arguments.value(QStringLiteral("full_name")).toString());
            }
            if (arguments.contains(QStringLiteral("special_units")))
            {
                measurements.SetMSpecialUnits(name, arguments.value(QStringLiteral("special_units")).toBool());
            }
            if (arguments.contains(QStringLiteral("dimension")))
            {
                if (measurements.Type() != MeasurementsType::Individual)
                {
                    throw std::invalid_argument("dimension is only valid for individual measurement files");
                }
                const QString dimension = arguments.value(QStringLiteral("dimension")).toString().toUpper();
                const QMap<QString, IMD> dimensions{{QStringLiteral("N"), IMD::N}, {QStringLiteral("X"), IMD::X},
                                                    {QStringLiteral("Y"), IMD::Y}, {QStringLiteral("W"), IMD::W},
                                                    {QStringLiteral("Z"), IMD::Z}};
                if (!dimensions.contains(dimension))
                {
                    throw std::invalid_argument("Individual measurement dimension must be N, X, Y, W, or Z");
                }
                measurements.SetMDimension(name, dimensions.value(dimension));
            }
            QJsonObject values = summary.value(QStringLiteral("measurements")).toObject();
            values.insert(name, arguments.value(QStringLiteral("value_mm")).toDouble());
            summary.insert(QStringLiteral("measurements"), values);
        }
        else if (action == QStringLiteral("measurement.rename"))
        {
            const QString name = RequiredString(arguments, QStringLiteral("name"));
            const QString newName = RequiredString(arguments, QStringLiteral("new_name"));
            if (!measurements.ListAll().contains(name) || measurements.ListAll().contains(newName))
            {
                throw std::invalid_argument("Measurement rename source is missing or destination already exists");
            }
            measurements.SetMName(name, newName);
        }
        else if (action == QStringLiteral("measurement.remove"))
        {
            const QString name = RequiredString(arguments, QStringLiteral("name"));
            if (!measurements.ListAll().contains(name))
            {
                throw std::invalid_argument("Measurement does not exist");
            }
            measurements.Remove(name);
        }
        else if (action == QStringLiteral("measurement.dimension_set"))
        {
            if (measurements.Type() != MeasurementsType::Multisize)
            {
                throw std::invalid_argument("dimension_set requires a multisize measurement file");
            }
            const QString axis = RequiredString(arguments, QStringLiteral("axis")).toUpper();
            MeasurementDimension type;
            if (axis == QStringLiteral("X"))
            {
                type = MeasurementDimension::X;
            }
            else if (axis == QStringLiteral("Y"))
            {
                type = MeasurementDimension::Y;
            }
            else if (axis == QStringLiteral("W"))
            {
                type = MeasurementDimension::W;
            }
            else if (axis == QStringLiteral("Z"))
            {
                type = MeasurementDimension::Z;
            }
            else
            {
                throw std::invalid_argument("Measurement dimension axis must be X, Y, W, or Z");
            }
            MeasurementDimension_p dimension = measurements.Dimensions().value(type);
            if (dimension.isNull())
            {
                throw std::invalid_argument("The requested dimension does not exist in the measurement file");
            }
            const auto fileValue = [&measurements](qreal millimetres) {
                return UnitConvertor(millimetres, Unit::Mm, measurements.Units());
            };
            if (arguments.contains(QStringLiteral("min_mm")))
            {
                dimension->SetMinValue(fileValue(arguments.value(QStringLiteral("min_mm")).toDouble()));
            }
            if (arguments.contains(QStringLiteral("max_mm")))
            {
                dimension->SetMaxValue(fileValue(arguments.value(QStringLiteral("max_mm")).toDouble()));
            }
            if (arguments.contains(QStringLiteral("step_mm")))
            {
                dimension->SetStep(fileValue(arguments.value(QStringLiteral("step_mm")).toDouble()));
            }
            if (arguments.contains(QStringLiteral("base_mm")))
            {
                dimension->SetBaseValue(fileValue(arguments.value(QStringLiteral("base_mm")).toDouble()));
            }
            if (arguments.contains(QStringLiteral("body_measurement")))
            {
                dimension->SetBodyMeasurement(arguments.value(QStringLiteral("body_measurement")).toBool());
            }
            if (arguments.contains(QStringLiteral("name")))
            {
                dimension->SetCustomName(arguments.value(QStringLiteral("name")).toString());
            }
            if (!dimension->IsValid())
            {
                throw std::invalid_argument(
                    QStringLiteral("Invalid %1 dimension: %2").arg(axis, dimension->Error()).toStdString());
            }
            measurements.SetDimensionDefinition(dimension);
            QJsonObject values = summary.value(QStringLiteral("measurements")).toObject();
            values.insert(QStringLiteral("dimension.%1.base_mm").arg(axis),
                          UnitConvertor(dimension->BaseValue(), measurements.Units(), Unit::Mm));
            summary.insert(QStringLiteral("measurements"), values);
        }
        else if (action == QStringLiteral("measurement.file_metadata_set"))
        {
            if (arguments.contains(QStringLiteral("notes")))
            {
                measurements.SetNotes(arguments.value(QStringLiteral("notes")).toString());
            }
            if (arguments.contains(QStringLiteral("customer")))
            {
                measurements.SetCustomer(arguments.value(QStringLiteral("customer")).toString());
            }
            if (arguments.contains(QStringLiteral("email")))
            {
                measurements.SetEmail(arguments.value(QStringLiteral("email")).toString());
            }
            if (arguments.contains(QStringLiteral("birth_date")))
            {
                const QDate date = QDate::fromString(arguments.value(QStringLiteral("birth_date")).toString(), Qt::ISODate);
                if (!date.isValid())
                {
                    throw std::invalid_argument("birth_date must be an ISO 8601 date");
                }
                measurements.SetBirthDate(date);
            }
            if (arguments.contains(QStringLiteral("gender")))
            {
                const QString gender = arguments.value(QStringLiteral("gender")).toString().toLower();
                if (gender == QStringLiteral("male"))
                {
                    measurements.SetGender(GenderType::Male);
                }
                else if (gender == QStringLiteral("female"))
                {
                    measurements.SetGender(GenderType::Female);
                }
                else if (gender == QStringLiteral("unknown"))
                {
                    measurements.SetGender(GenderType::Unknown);
                }
                else
                {
                    throw std::invalid_argument("gender must be male, female, or unknown");
                }
            }
            if (arguments.contains(QStringLiteral("known_measurements_uuid")))
            {
                const QUuid id(arguments.value(QStringLiteral("known_measurements_uuid")).toString());
                if (id.isNull())
                {
                    throw std::invalid_argument("known_measurements_uuid must be a UUID");
                }
                measurements.SetKnownMeasurements(id);
            }
            if (arguments.contains(QStringLiteral("read_only")))
            {
                measurements.SetReadOnly(arguments.value(QStringLiteral("read_only")).toBool());
            }
            if (arguments.contains(QStringLiteral("full_circumference")))
            {
                measurements.SetFullCircumference(arguments.value(QStringLiteral("full_circumference")).toBool());
            }
        }
        else if (action == QStringLiteral("measurement.dimension_labels_set"))
        {
            if (measurements.Type() != MeasurementsType::Multisize)
            {
                throw std::invalid_argument("dimension_labels_set requires a multisize measurement file");
            }
            const QString axis = RequiredString(arguments, QStringLiteral("axis")).toUpper();
            const QMap<QString, MeasurementDimension> types{{QStringLiteral("X"), MeasurementDimension::X},
                                                            {QStringLiteral("Y"), MeasurementDimension::Y},
                                                            {QStringLiteral("W"), MeasurementDimension::W},
                                                            {QStringLiteral("Z"), MeasurementDimension::Z}};
            if (!types.contains(axis) || !measurements.Dimensions().contains(types.value(axis)))
            {
                throw std::invalid_argument("The requested dimension does not exist in the measurement file");
            }
            DimesionLabels labels;
            for (const QJsonValue value : arguments.value(QStringLiteral("labels")).toArray())
            {
                const QJsonObject label = value.toObject();
                labels.insert(UnitConvertor(label.value(QStringLiteral("value_mm")).toDouble(), Unit::Mm,
                                            measurements.Units()),
                              RequiredString(label, QStringLiteral("label")));
            }
            measurements.SetDimensionLabels({{types.value(axis), labels}});
        }
        else if (action == QStringLiteral("measurement.restriction_set") ||
                 action == QStringLiteral("measurement.restriction_remove"))
        {
            const auto fileValue = [&measurements](qreal millimetres) {
                return UnitConvertor(millimetres, Unit::Mm, measurements.Units());
            };
            const qreal baseA = fileValue(arguments.value(QStringLiteral("base_a_mm")).toDouble());
            const qreal baseB = fileValue(arguments.value(QStringLiteral("base_b_mm")).toDouble());
            const QString key = VMeasurement::CorrectionHash(baseA, baseB);
            QMap<QString, VDimensionRestriction> restrictions = measurements.GetRestrictions();
            if (action == QStringLiteral("measurement.restriction_remove"))
            {
                restrictions.remove(key);
            }
            else
            {
                QSet<qreal> excluded;
                for (const QJsonValue value : arguments.value(QStringLiteral("exclude_mm")).toArray())
                {
                    excluded.insert(fileValue(value.toDouble()));
                }
                VDimensionRestriction restriction(fileValue(arguments.value(QStringLiteral("min_mm")).toDouble()),
                                                  fileValue(arguments.value(QStringLiteral("max_mm")).toDouble()));
                restriction.SetExcludeValues(excluded);
                restrictions.insert(key, restriction);
            }
            measurements.SetRestrictions(restrictions);
        }
        else if (action == QStringLiteral("measurement.correction_set"))
        {
            const QString name = RequiredString(arguments, QStringLiteral("name"));
            if (!measurements.ListAll().contains(name))
            {
                throw std::invalid_argument("Measurement does not exist");
            }
            const auto fileValue = [&measurements](qreal millimetres) {
                return UnitConvertor(millimetres, Unit::Mm, measurements.Units());
            };
            measurements.SetMCorrectionValue(name, fileValue(arguments.value(QStringLiteral("base_a_mm")).toDouble()),
                                             fileValue(arguments.value(QStringLiteral("base_b_mm")).toDouble()),
                                             fileValue(arguments.value(QStringLiteral("base_c_mm")).toDouble()),
                                             fileValue(arguments.value(QStringLiteral("value_mm")).toDouble()));
        }
        else if (action == QStringLiteral("measurement.value_alias_set"))
        {
            const QString name = RequiredString(arguments, QStringLiteral("name"));
            const QString alias = RequiredString(arguments, QStringLiteral("alias"));
            if (!measurements.ListAll().contains(name))
            {
                throw std::invalid_argument("Measurement does not exist");
            }
            if (arguments.contains(QStringLiteral("base_a_mm")))
            {
                const auto fileValue = [&measurements](qreal millimetres) {
                    return UnitConvertor(millimetres, Unit::Mm, measurements.Units());
                };
                measurements.SetMValueAlias(name, fileValue(arguments.value(QStringLiteral("base_a_mm")).toDouble()),
                                            fileValue(arguments.value(QStringLiteral("base_b_mm")).toDouble()),
                                            fileValue(arguments.value(QStringLiteral("base_c_mm")).toDouble()), alias);
            }
            else
            {
                measurements.SetMValueAlias(name, alias);
            }
        }
        else if (action == QStringLiteral("measurement.image_set") ||
                 action == QStringLiteral("measurement.image_remove"))
        {
            const QString name = RequiredString(arguments, QStringLiteral("name"));
            if (!measurements.ListAll().contains(name))
            {
                throw std::invalid_argument("Measurement does not exist");
            }
            VPatternImage image;
            if (action == QStringLiteral("measurement.image_set"))
            {
                const QString source = QFileInfo(RequiredString(arguments, QStringLiteral("source_path"))).absoluteFilePath();
                if (!QFileInfo::exists(source))
                {
                    throw std::invalid_argument("Measurement image does not exist");
                }
                image = VPatternImage::FromFile(source);
                if (!image.IsValid())
                {
                    throw std::invalid_argument(
                        QStringLiteral("Invalid measurement image: %1").arg(image.ErrorString()).toStdString());
                }
            }
            measurements.SetMImage(name, image);
        }
        else if (action == QStringLiteral("measurement.import_csv"))
        {
            const QString source = QFileInfo(RequiredString(arguments, QStringLiteral("source_path"))).absoluteFilePath();
            if (!QFileInfo::exists(source))
            {
                throw std::invalid_argument("Measurement CSV does not exist");
            }
            const QString separatorText = arguments.value(QStringLiteral("separator")).toString(QStringLiteral(","));
            if (separatorText.isEmpty())
            {
                throw std::invalid_argument("CSV separator cannot be empty");
            }
            const bool withHeader = arguments.value(QStringLiteral("with_header")).toBool(true);
            const QxtCsvModel csv(source, nullptr, withHeader, separatorText.at(0), nullptr);
            const bool individual = measurements.Type() == MeasurementsType::Individual;
            const int minimumColumns = individual ? 2 : 5;
            if (csv.columnCount() < minimumColumns)
            {
                throw std::invalid_argument(
                    QStringLiteral("Measurement CSV requires at least %1 columns").arg(minimumColumns).toStdString());
            }
            const auto fileValue = [&measurements](const QString &text) {
                bool ok = false;
                const qreal millimetres = text.toDouble(&ok);
                if (!ok)
                {
                    throw std::invalid_argument(QStringLiteral("Invalid millimetre value in CSV: %1").arg(text).toStdString());
                }
                return UnitConvertor(millimetres, Unit::Mm, measurements.Units());
            };
            for (int row = 0; row < csv.rowCount(); ++row)
            {
                const QString name = csv.text(row, 0).simplified();
                if (name.isEmpty())
                {
                    throw std::invalid_argument(QStringLiteral("Empty measurement name in CSV row %1").arg(row + 1).toStdString());
                }
                if (!measurements.ListAll().contains(name))
                {
                    measurements.AddEmpty(name);
                }
                if (individual)
                {
                    QString value = csv.text(row, 1).simplified();
                    bool numeric = false;
                    const qreal millimetres = value.toDouble(&numeric);
                    if (numeric)
                    {
                        value = QString::number(UnitConvertor(millimetres, Unit::Mm, measurements.Units()), 'g', 15);
                    }
                    measurements.SetMValue(name, value);
                    if (csv.columnCount() > 2) measurements.SetMFullName(name, csv.text(row, 2).simplified());
                    if (csv.columnCount() > 3) measurements.SetMDescription(name, csv.text(row, 3).simplified());
                    if (csv.columnCount() > 4) measurements.SetMSpecialUnits(name, csv.text(row, 4).toInt() != 0);
                }
                else
                {
                    measurements.SetMBaseValue(name, fileValue(csv.text(row, 1)));
                    measurements.SetMShiftA(name, fileValue(csv.text(row, 2)));
                    measurements.SetMShiftB(name, fileValue(csv.text(row, 3)));
                    measurements.SetMShiftC(name, fileValue(csv.text(row, 4)));
                    if (csv.columnCount() > 5) measurements.SetMFullName(name, csv.text(row, 5).simplified());
                    if (csv.columnCount() > 6) measurements.SetMDescription(name, csv.text(row, 6).simplified());
                    if (csv.columnCount() > 7) measurements.SetMSpecialUnits(name, csv.text(row, 7).toInt() != 0);
                }
            }
        }

        QString error;
        if (!measurements.SaveDocument(path, error))
        {
            throw std::runtime_error(QStringLiteral("Unable to save measurement file: %1").arg(error).toStdString());
        }
        attachMeasurement(path);
        reloadMeasurement(path);
        return;
    }

    if (action == QStringLiteral("measurement.export_csv"))
    {
        const QString sourcePath = measurementPath(arguments);
        Unit unit = Unit::Mm;
        VContainer data(VAbstractApplication::VApp()->TrVars(), &unit, VContainer::UniqueNamespace());
        VMeasurements measurements(&data);
        measurements.setXMLContent(sourcePath);
        measurements.StoreNames(false);
        measurements.ReadMeasurements(measurements.DimensionABase(), measurements.DimensionBBase(),
                                      measurements.DimensionCBase());

        QJsonObject outputArguments;
        outputArguments.insert(
            QStringLiteral("path"),
            arguments.value(QStringLiteral("output_path")).toString(QStringLiteral("measurements/export.csv")));
        const QString outputPath = measurementPath(outputArguments);
        QDir().mkpath(QFileInfo(outputPath).absolutePath());
        QSaveFile output(outputPath);
        if (!output.open(QIODevice::WriteOnly | QIODevice::Text))
        {
            throw std::runtime_error("Unable to open measurement CSV output");
        }
        QTextStream stream(&output);
        const QString separatorText =
            arguments.value(QStringLiteral("separator")).toString(QStringLiteral(","));
        if (separatorText.size() != 1 || separatorText.at(0) == QLatin1Char('\n') ||
            separatorText.at(0) == QLatin1Char('\r') || separatorText.at(0) == QLatin1Char('"'))
        {
            throw std::invalid_argument("CSV separator must be one character other than a quote or newline");
        }
        const QChar separator = separatorText.at(0);
        if (measurements.Type() == MeasurementsType::Individual)
        {
            stream << "name" << separator << "value_mm" << separator << "full_name" << separator << "description"
                   << separator << "formula\n";
        }
        else
        {
            stream << "name" << separator << "base_mm" << separator << "shift_a_mm" << separator << "shift_b_mm"
                   << separator << "shift_c_mm" << separator << "full_name" << separator << "description\n";
        }
        for (const QString &name : measurements.ListAll())
        {
            const QSharedPointer<VMeasurement> item = data.GetVariable<VMeasurement>(name);
            stream << CsvCell(name) << separator;
            if (measurements.Type() == MeasurementsType::Individual)
            {
                stream << QString::number(UnitConvertor(*item->GetValue(), measurements.Units(), Unit::Mm), 'g', 15)
                       << separator << CsvCell(item->GetGuiText()) << separator << CsvCell(item->GetDescription())
                       << separator << CsvCell(item->GetFormula()) << '\n';
            }
            else
            {
                stream << QString::number(UnitConvertor(item->GetBase(), measurements.Units(), Unit::Mm), 'g', 15)
                       << separator
                       << QString::number(UnitConvertor(item->GetShiftA(), measurements.Units(), Unit::Mm), 'g', 15)
                       << separator
                       << QString::number(UnitConvertor(item->GetShiftB(), measurements.Units(), Unit::Mm), 'g', 15)
                       << separator
                       << QString::number(UnitConvertor(item->GetShiftC(), measurements.Units(), Unit::Mm), 'g', 15)
                       << separator << CsvCell(item->GetGuiText()) << separator << CsvCell(item->GetDescription())
                       << '\n';
            }
        }
        if (!output.commit())
        {
            throw std::runtime_error("Unable to commit measurement CSV output");
        }
        QJsonObject values = summary.value(QStringLiteral("measurements")).toObject();
        values.insert(QStringLiteral("csv.rows"), measurements.ListAll().size());
        summary.insert(QStringLiteral("measurements"), values);
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
        const QJsonObject reference = operation.value(QStringLiteral("target")).toObject();
        const quint32 nativeId = ResolveObject(reference, aliases);
        QString semanticAlias = reference.value(QStringLiteral("alias")).toString();
        QString uuid = reference.value(QStringLiteral("uuid")).toString();
        QString kind;
        const QJsonObject objects = aliases.value(QStringLiteral("objects")).toObject();
        for (auto iterator = objects.constBegin(); iterator != objects.constEnd(); ++iterator)
        {
            const QJsonObject record = iterator.value().toObject();
            if (!record.value(QStringLiteral("deleted")).toBool() &&
                static_cast<quint32>(record.value(QStringLiteral("native_id")).toInteger()) == nativeId)
            {
                uuid = iterator.key();
                semanticAlias = record.value(QStringLiteral("alias")).toString();
                kind = record.value(QStringLiteral("kind")).toString();
                break;
            }
        }

        // Pieces and piece paths live in dedicated VContainer maps rather than the geometric-object map.
        if (kind == QStringLiteral("Piece"))
        {
            static_cast<void>(m_window->pattern->GetPiece(nativeId));
        }
        else if (kind == QStringLiteral("PiecePath"))
        {
            static_cast<void>(m_window->pattern->GetPiecePath(nativeId));
        }
        else if (kind == QStringLiteral("Group"))
        {
            if (!m_window->doc->GetGroups().contains(nativeId))
            {
                throw std::invalid_argument("The semantic group no longer exists in the pattern");
            }
        }
        else
        {
            static_cast<void>(m_window->pattern->GetGObject(nativeId));
        }
        QJsonArray changed = summary.value(QStringLiteral("changed")).toArray();
        changed.append(QJsonObject{{QStringLiteral("uuid"), uuid.isEmpty() ? QJsonValue(QJsonValue::Null)
                                                                           : QJsonValue(uuid)},
                                   {QStringLiteral("alias"), semanticAlias}});
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
                line->SetLineColor(
                    CanonicalToolColor(RequiredString(arguments, QStringLiteral("line_color"))));
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
                curve->SetLineColor(
                    CanonicalToolColor(RequiredString(arguments, QStringLiteral("line_color"))));
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
        initData.name = NativeObjectName(arguments);
        initData.x = UnitConvertor(arguments.value(QStringLiteral("x_mm")).toDouble(), Unit::Mm, Unit::Px);
        initData.y = UnitConvertor(arguments.value(QStringLiteral("y_mm")).toDouble(), Unit::Mm, Unit::Px);
        auto *tool = CreateToolFromCommand<VToolBasePoint>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(alias, QStringLiteral("BasePoint"), tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.line"))
    {
        VToolLineCommandData command;
        command.firstPoint = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        command.secondPoint = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        command.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        command.lineColor = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        command.notes = arguments.value(QStringLiteral("notes")).toString();
        VToolLine *tool = nullptr;
        if (m_constructionAdapter == QStringLiteral("gui_dialog"))
        {
            DialogLine dialog(m_window->pattern, m_window->doc, NULL_ID);
            dialog.SetFirstPoint(command.firstPoint);
            dialog.SetSecondPoint(command.secondPoint);
            dialog.SetTypeLine(command.typeLine);
            dialog.SetLineColor(command.lineColor);
            dialog.SetNotes(command.notes);
            tool = VToolLine::Create(QPointer<DialogTool>(&dialog), m_window->m_sceneDraw, m_window->doc,
                                     m_window->pattern);
        }
        else
        {
            tool = VToolLine::Create(command, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        }
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Line"), tool->getId(),
                       aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.along_line"))
    {
        VToolAlongLineCommandData command;
        command.name = NativeObjectName(arguments);
        command.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        command.secondPointId = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        command.formula = arguments.contains(QStringLiteral("formula"))
                              ? RequiredString(arguments, QStringLiteral("formula"))
                              : NativeFormulaForMillimetres(arguments.value(QStringLiteral("length_mm")).toDouble());
        command.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        command.lineColor = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        command.notes = arguments.value(QStringLiteral("notes")).toString();
        VToolAlongLine *tool = nullptr;
        if (m_constructionAdapter == QStringLiteral("gui_dialog"))
        {
            DialogAlongLine dialog(m_window->pattern, m_window->doc, NULL_ID);
            dialog.SetFormula(command.formula);
            dialog.SetFirstPointId(command.firstPointId);
            dialog.SetSecondPointId(command.secondPointId);
            dialog.SetTypeLine(command.typeLine);
            dialog.SetLineColor(command.lineColor);
            dialog.SetPointName(command.name);
            dialog.SetNotes(command.notes);
            tool = VToolAlongLine::Create(QPointer<DialogTool>(&dialog), m_window->m_sceneDraw, m_window->doc,
                                          m_window->pattern);
        }
        else
        {
            tool = VToolAlongLine::Create(command, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        }
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("AlongLine"), tool->getId(),
                       aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.midpoint"))
    {
        VToolAlongLineCommandData command;
        command.name = NativeObjectName(arguments);
        command.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        command.secondPointId = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        command.formula = currentLength + QStringLiteral("/2");
        command.notes = arguments.value(QStringLiteral("notes")).toString();
        VToolAlongLine *tool = nullptr;
        if (m_constructionAdapter == QStringLiteral("gui_dialog"))
        {
            DialogAlongLine dialog(m_window->pattern, m_window->doc, NULL_ID);
            dialog.SetFormula(command.formula);
            dialog.SetFirstPointId(command.firstPointId);
            dialog.SetSecondPointId(command.secondPointId);
            dialog.SetTypeLine(command.typeLine);
            dialog.SetLineColor(command.lineColor);
            dialog.SetPointName(command.name);
            dialog.SetNotes(command.notes);
            tool = VToolAlongLine::Create(QPointer<DialogTool>(&dialog), m_window->m_sceneDraw, m_window->doc,
                                          m_window->pattern);
        }
        else
        {
            tool = VToolAlongLine::Create(command, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        }
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("AlongLine"), tool->getId(),
                       aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.end_line"))
    {
        VToolEndLineCommandData command;
        command.name = NativeObjectName(arguments);
        command.basePointId = ResolveObject(arguments.value(QStringLiteral("base_point")).toObject(), aliases);
        command.formulaLength = arguments.contains(QStringLiteral("formula_length"))
                                    ? RequiredString(arguments, QStringLiteral("formula_length"))
                                    : NativeFormulaForMillimetres(
                                          arguments.value(QStringLiteral("length_mm")).toDouble());
        command.formulaAngle = arguments.contains(QStringLiteral("formula_angle"))
                                   ? RequiredString(arguments, QStringLiteral("formula_angle"))
                                   : QString::number(arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g',
                                                     15);
        command.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        command.lineColor = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        command.notes = arguments.value(QStringLiteral("notes")).toString();
        VToolEndLine *tool = nullptr;
        if (m_constructionAdapter == QStringLiteral("gui_dialog"))
        {
            DialogEndLine dialog(m_window->pattern, m_window->doc, NULL_ID);
            dialog.SetFormula(command.formulaLength);
            dialog.SetAngle(command.formulaAngle);
            dialog.SetBasePointId(command.basePointId);
            dialog.SetTypeLine(command.typeLine);
            dialog.SetLineColor(command.lineColor);
            dialog.SetPointName(command.name);
            dialog.SetNotes(command.notes);
            tool = VToolEndLine::Create(QPointer<DialogTool>(&dialog), m_window->m_sceneDraw, m_window->doc,
                                        m_window->pattern);
        }
        else
        {
            tool = VToolEndLine::Create(command, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        }
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("EndLine"), tool->getId(),
                       aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.p1Line1Id = ResolveObject(arguments.value(QStringLiteral("line1_p1")).toObject(), aliases);
        initData.p2Line1Id = ResolveObject(arguments.value(QStringLiteral("line1_p2")).toObject(), aliases);
        initData.p1Line2Id = ResolveObject(arguments.value(QStringLiteral("line2_p1")).toObject(), aliases);
        initData.p2Line2Id = ResolveObject(arguments.value(QStringLiteral("line2_p2")).toObject(), aliases);
        auto *tool = CreateToolFromCommand<VToolLineIntersect>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("LineIntersect"),
                       tool->getId(), aliases, summary);
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
        initData.color = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        auto *tool = CreateToolFromCommand<VToolArc>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
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
        initData.color = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        auto *tool = CreateToolFromCommand<VToolArcWithLength>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
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
            initData.color = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
            initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
            initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
            auto *tool = CreateToolFromCommand<VToolEllipticalArc>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
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
        initData.color = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        auto *tool = CreateToolFromCommand<VToolEllipticalArcWithLength>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
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
        initData.color = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        auto *tool = CreateToolFromCommand<VToolSpline>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
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
        initData.spline->SetColor(CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack)));
        initData.spline->SetPenStyle(arguments.value(QStringLiteral("line_type")).toString(TypeLineLine));
        initData.spline->SetAliasSuffix(arguments.value(QStringLiteral("native_alias_suffix")).toString());
        auto *tool = CreateToolFromCommand<VToolCubicBezier>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
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
        initData.color = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
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
        auto *tool = CreateToolFromCommand<VToolSplinePath>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
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
        initData.path->SetColor(CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack)));
        initData.path->SetPenStyle(arguments.value(QStringLiteral("line_type")).toString(TypeLineLine));
        initData.path->SetAliasSuffix(arguments.value(QStringLiteral("native_alias_suffix")).toString());
        auto *tool = CreateToolFromCommand<VToolCubicBezierPath>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("CubicBezierPath"),
                       tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.parallel_curve"))
    {
        VToolParallelCurveInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.originCurveId = ResolveObject(arguments.value(QStringLiteral("curve")).toObject(), aliases);
        initData.formulaWidth = arguments.contains(QStringLiteral("formula_width"))
                                    ? RequiredString(arguments, QStringLiteral("formula_width"))
                                    : NativeFormulaForMillimetres(
                                          arguments.value(QStringLiteral("width_mm")).toDouble());
        initData.name = NativeObjectName(arguments);
        initData.color = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        auto *tool = CreateToolFromCommand<VToolParallelCurve>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("ParallelCurve"),
                       tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.graduated_curve"))
    {
        const QJsonArray offsetValues = arguments.value(QStringLiteral("offsets")).toArray();
        if (offsetValues.size() < 2)
        {
            throw std::invalid_argument("graduated_curve requires at least two offsets");
        }

        VToolGraduatedCurveInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.originCurveId = ResolveObject(arguments.value(QStringLiteral("curve")).toObject(), aliases);
        initData.name = NativeObjectName(arguments);
        initData.color = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        initData.penStyle = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.aliasSuffix = arguments.value(QStringLiteral("native_alias_suffix")).toString();
        for (qsizetype index = 0; index < offsetValues.size(); ++index)
        {
            const QJsonObject offset = offsetValues.at(index).toObject();
            VRawGraduatedCurveOffset raw;
            raw.name = offset.value(QStringLiteral("name")).toString(
                QStringLiteral("offset_%1").arg(index + 1));
            raw.formula = offset.contains(QStringLiteral("formula"))
                              ? RequiredString(offset, QStringLiteral("formula"))
                              : NativeFormulaForMillimetres(
                                    offset.value(QStringLiteral("width_mm")).toDouble());
            raw.description = offset.value(QStringLiteral("description")).toString();
            initData.offsets.append(raw);
        }
        auto *tool = CreateToolFromCommand<VToolGraduatedCurve>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("GraduatedCurve"),
                       tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.piece"))
    {
        const QJsonArray nodeValues = arguments.value(QStringLiteral("nodes")).toArray();
        if (nodeValues.size() < 3)
        {
            throw std::invalid_argument("piece requires at least three path nodes");
        }

        VPiecePath path(PiecePathType::PiecePath);
        for (const QJsonValue value : nodeValues)
        {
            const QJsonObject item = value.toObject();
            VPieceNode node(ResolveObject(item.value(QStringLiteral("object")).toObject(), aliases),
                            PieceNodeTool(item.value(QStringLiteral("type")).toString(QStringLiteral("point"))),
                            item.value(QStringLiteral("reverse")).toBool());
            node.SetExcluded(item.value(QStringLiteral("excluded")).toBool());
            node.SetPassmark(item.value(QStringLiteral("passmark")).toBool());
            if (item.contains(QStringLiteral("seam_before_formula")))
            {
                node.SetFormulaSABefore(RequiredString(item, QStringLiteral("seam_before_formula")));
            }
            if (item.contains(QStringLiteral("seam_after_formula")))
            {
                node.SetFormulaSAAfter(RequiredString(item, QStringLiteral("seam_after_formula")));
            }
            path.Append(node);
        }

        const QString width = arguments.contains(QStringLiteral("seam_allowance_formula"))
                                  ? RequiredString(arguments, QStringLiteral("seam_allowance_formula"))
                                  : NativeFormulaForMillimetres(
                                        arguments.value(QStringLiteral("seam_allowance_mm")).toDouble());
        QString checkedWidth = width;
        const qreal calculatedWidth = VAbstractTool::CheckFormula(NULL_ID, checkedWidth, m_window->pattern);

        VPiece piece;
        piece.SetName(arguments.value(QStringLiteral("name")).toString(
            RequiredString(arguments, QStringLiteral("alias"))));
        piece.SetShortName(arguments.value(QStringLiteral("short_name")).toString());
        piece.SetUUID(QUuid::createUuid());
        piece.SetPath(path);
        piece.SetSeamAllowance(arguments.value(QStringLiteral("seam_allowance")).toBool(true));
        piece.SetSeamAllowanceBuiltIn(
            arguments.value(QStringLiteral("seam_allowance_built_in")).toBool(false));
        piece.SetFormulaSAWidth(checkedWidth, calculatedWidth);
        piece.SetForbidFlipping(arguments.value(QStringLiteral("forbid_flipping")).toBool(false));
        piece.SetFollowGrainline(arguments.value(QStringLiteral("follow_grainline")).toBool(false));
        piece.GetPath().SetNodes(
            VToolSeamAllowance::PrepareNodesForCommand(piece.GetPath(), m_window->m_sceneDetails, m_window->doc,
                                                       m_window->pattern));

        VToolSeamAllowanceInitData initData;
        initData.scene = m_window->m_sceneDetails;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.detail = piece;
        initData.width = checkedWidth;
        auto *tool = CreateToolFromCommand<VToolSeamAllowance>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Piece"), tool->getId(),
                       aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.piece_path"))
    {
        const QJsonArray nodeValues = arguments.value(QStringLiteral("nodes")).toArray();
        if (nodeValues.size() < 2)
        {
            throw std::invalid_argument("piece path requires at least two nodes");
        }

        VPiecePath path(PiecePathKind(
            arguments.value(QStringLiteral("type")).toString(QStringLiteral("internal"))));
        path.SetName(arguments.value(QStringLiteral("name")).toString(
            RequiredString(arguments, QStringLiteral("alias"))));
        path.SetPenType(LineStyleToPenStyle(
            arguments.value(QStringLiteral("line_type")).toString(TypeLineLine)));
        path.SetVisibilityTrigger(
            arguments.value(QStringLiteral("visibility_formula")).toString(QStringLiteral("1")));
        path.SetCutPath(arguments.value(QStringLiteral("cut")).toBool(false));
        path.SetFirstToCuttingContour(arguments.value(QStringLiteral("first_to_contour")).toBool(false));
        path.SetLastToCuttingContour(arguments.value(QStringLiteral("last_to_contour")).toBool(false));
        path.SetNotMirrored(arguments.value(QStringLiteral("not_mirrored")).toBool(false));
        for (const QJsonValue value : nodeValues)
        {
            const QJsonObject item = value.toObject();
            VPieceNode node(ResolveObject(item.value(QStringLiteral("object")).toObject(), aliases),
                            PieceNodeTool(item.value(QStringLiteral("type")).toString(QStringLiteral("point"))),
                            item.value(QStringLiteral("reverse")).toBool());
            node.SetExcluded(item.value(QStringLiteral("excluded")).toBool());
            path.Append(node);
        }
        path.SetNodes(VToolSeamAllowance::PrepareNodesForCommand(path, m_window->m_sceneDetails, m_window->doc,
                                                                 m_window->pattern));

        VToolPiecePathInitData initData;
        initData.path = path;
        initData.idObject = ResolveObject(arguments.value(QStringLiteral("piece")).toObject(), aliases);
        initData.scene = m_window->m_sceneDetails;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        auto *tool = CreateToolFromCommand<VToolPiecePath>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        if (tool == nullptr)
        {
            throw std::runtime_error("Valentina did not create the piece path");
        }
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("PiecePath"), tool->getId(),
                       aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.pin"))
    {
        VToolPinInitData initData;
        initData.pointId = ResolveObject(arguments.value(QStringLiteral("point")).toObject(), aliases);
        initData.idObject = ResolveObject(arguments.value(QStringLiteral("piece")).toObject(), aliases);
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        auto *tool = CreateToolFromCommand<VToolPin>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        if (tool == nullptr)
        {
            throw std::runtime_error("Valentina did not create the pin");
        }
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Pin"), tool->getId(), aliases,
                       summary);
        return;
    }

    if (action == QStringLiteral("pattern.place_label"))
    {
        VToolPlaceLabelInitData initData;
        initData.centerPoint = ResolveObject(arguments.value(QStringLiteral("center_point")).toObject(), aliases);
        initData.idObject = ResolveObject(arguments.value(QStringLiteral("piece")).toObject(), aliases);
        initData.width = arguments.contains(QStringLiteral("width_formula"))
                             ? RequiredString(arguments, QStringLiteral("width_formula"))
                             : NativeFormulaForMillimetres(arguments.value(QStringLiteral("width_mm")).toDouble());
        initData.height = arguments.contains(QStringLiteral("height_formula"))
                              ? RequiredString(arguments, QStringLiteral("height_formula"))
                              : NativeFormulaForMillimetres(arguments.value(QStringLiteral("height_mm")).toDouble());
        initData.angle = arguments.value(QStringLiteral("angle_formula"))
                             .toString(QString::number(arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g', 15));
        initData.visibilityTrigger =
            arguments.value(QStringLiteral("visibility_formula")).toString(QStringLiteral("1"));
        initData.notMirrored = arguments.value(QStringLiteral("not_mirrored")).toBool(false);
        initData.type = PlaceLabelKind(
            arguments.value(QStringLiteral("type")).toString(QStringLiteral("button")));
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        auto *tool = CreateToolFromCommand<VToolPlaceLabel>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        if (tool == nullptr)
        {
            throw std::runtime_error("Valentina did not create the place label");
        }
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("PlaceLabel"), tool->getId(),
                       aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.insert_node"))
    {
        const quint32 pieceId = ResolveObject(arguments.value(QStringLiteral("piece")).toObject(), aliases);
        const QJsonArray nodeValues = arguments.value(QStringLiteral("nodes")).toArray();
        if (nodeValues.isEmpty())
        {
            throw std::invalid_argument("insert_node requires at least one node");
        }
        QVector<VPieceNode> nodes;
        nodes.reserve(nodeValues.size());
        for (const QJsonValue value : nodeValues)
        {
            const QJsonObject item = value.toObject();
            VPieceNode node(ResolveObject(item.value(QStringLiteral("object")).toObject(), aliases),
                            PieceNodeTool(item.value(QStringLiteral("type")).toString(QStringLiteral("point"))),
                            item.value(QStringLiteral("reverse")).toBool());
            node.SetExcluded(item.value(QStringLiteral("excluded")).toBool());
            node.SetPassmark(item.value(QStringLiteral("passmark")).toBool());
            nodes.append(node);
        }
        VToolSeamAllowance::InsertNodes(nodes, pieceId, m_window->m_sceneDetails, m_window->pattern, m_window->doc);
        // InsertNodes updates the shared container and piece XML through undo, while duplicate-detail deliberately
        // reads the source tool's snapshot. Refresh that snapshot so subsequent operations in this same change-set
        // see newly created calculation objects and the updated path.
        m_window->doc->UpdateToolData(pieceId, m_window->pattern);

        const QJsonObject objects = aliases.value(QStringLiteral("objects")).toObject();
        QJsonArray changed = summary.value(QStringLiteral("changed")).toArray();
        for (auto iterator = objects.constBegin(); iterator != objects.constEnd(); ++iterator)
        {
            const QJsonObject record = iterator.value().toObject();
            if (!record.value(QStringLiteral("deleted")).toBool() &&
                static_cast<quint32>(record.value(QStringLiteral("native_id")).toInteger()) == pieceId)
            {
                changed.append(QJsonObject{{QStringLiteral("uuid"), iterator.key()},
                                           {QStringLiteral("alias"), record.value(QStringLiteral("alias"))}});
                break;
            }
        }
        summary.insert(QStringLiteral("changed"), changed);
        return;
    }

    if (action == QStringLiteral("pattern.duplicate_detail"))
    {
        const quint32 sourceId = ResolveObject(arguments.value(QStringLiteral("piece")).toObject(), aliases);
        VToolSeamAllowanceInitData initData;
        initData.scene = m_window->m_sceneDetails;
        initData.doc = m_window->doc;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.drawName = m_window->doc->PieceDrawName(sourceId);

        VContainer toolData = VAbstractPattern::getTool(sourceId)->GetDataCopy();
        initData.data = &toolData;
        VPiece detail = initData.data->GetPiece(sourceId);
        if (arguments.contains(QStringLiteral("name")))
        {
            detail.SetName(RequiredString(arguments, QStringLiteral("name")));
        }
        if (arguments.contains(QStringLiteral("short_name")))
        {
            detail.SetShortName(RequiredString(arguments, QStringLiteral("short_name")));
        }
        detail.SetMx(detail.GetMx() + VAbstractValApplication::VApp()->toPixel(
                                          arguments.value(QStringLiteral("offset_x_mm")).toDouble()));
        detail.SetMy(detail.GetMy() + VAbstractValApplication::VApp()->toPixel(
                                          arguments.value(QStringLiteral("offset_y_mm")).toDouble()));
        initData.detail = detail;
        initData.width = detail.GetFormulaSAWidth();
        auto *tool = VToolSeamAllowance::Duplicate(initData);
        if (tool == nullptr)
        {
            throw std::runtime_error("Valentina did not duplicate the piece");
        }
        tool->RefreshGeometry(true);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Piece"), tool->getId(), aliases,
                       summary);
        return;
    }

    if (action == QStringLiteral("pattern.object_duplicate"))
    {
        const QJsonObject source = arguments.value(QStringLiteral("source")).toObject();
        QJsonObject item{{QStringLiteral("source"), source},
                         {QStringLiteral("alias"), RequiredString(arguments, QStringLiteral("alias"))}};
        if (arguments.contains(QStringLiteral("name")))
        {
            item.insert(QStringLiteral("name"), RequiredString(arguments, QStringLiteral("name")));
        }
        const QJsonArray items{item};
        VToolMoveInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        QJsonObject rotationOrigin = arguments.value(QStringLiteral("rotation_origin")).toObject();
        if (rotationOrigin.isEmpty())
        {
            rotationOrigin = source;
        }
        initData.rotationOrigin = ResolveObject(rotationOrigin, aliases);
        initData.formulaLength = arguments.contains(QStringLiteral("formula_length"))
                                     ? RequiredString(arguments, QStringLiteral("formula_length"))
                                     : NativeFormulaForMillimetres(
                                           arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.formulaAngle = arguments.contains(QStringLiteral("formula_angle"))
                                    ? RequiredString(arguments, QStringLiteral("formula_angle"))
                                    : QString::number(
                                          arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g', 15);
        initData.formulaRotationAngle = QStringLiteral("0");
        initData.source = operationSources(items);
        CreateToolFromCommand<VToolMove>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        registerDestinations(items, initData.destination, QStringLiteral("DuplicatedObject"));
        return;
    }

    if (action == QStringLiteral("pattern.group"))
    {
        const QJsonArray objectValues = arguments.value(QStringLiteral("objects")).toArray();
        if (objectValues.isEmpty())
        {
            throw std::invalid_argument("group requires at least one object");
        }
        QMap<quint32, quint32> groupData;
        for (const QJsonValue value : objectValues)
        {
            const QJsonObject item = value.toObject();
            QJsonObject objectReference = item.value(QStringLiteral("object")).toObject();
            if (objectReference.isEmpty())
            {
                objectReference = item;
            }
            const quint32 objectId = ResolveObject(objectReference, aliases);
            QJsonObject toolReference = item.value(QStringLiteral("tool")).toObject();
            const quint32 toolId = toolReference.isEmpty() ? objectId : ResolveObject(toolReference, aliases);
            groupData.insert(objectId, toolId);
        }
        QStringList tags;
        for (const QJsonValue value : arguments.value(QStringLiteral("tags")).toArray())
        {
            if (!value.toString().isEmpty())
            {
                tags.append(value.toString());
            }
        }
        const quint32 groupId = m_window->pattern->getNextId();
        const QDomElement group = m_window->doc->CreateGroup(
            groupId,
            arguments.value(QStringLiteral("name")).toString(
                RequiredString(arguments, QStringLiteral("alias"))),
            tags, groupData);
        if (group.isNull())
        {
            throw std::runtime_error("Valentina did not create the group element");
        }
        VAbstractApplication::VApp()->getUndoStack()->push(new AddGroup(group, m_window->doc));
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Group"), groupId, aliases,
                       summary);
        return;
    }

    if (action == QStringLiteral("pattern.union_details"))
    {
        const quint32 firstPiece = ResolveObject(arguments.value(QStringLiteral("piece1")).toObject(), aliases);
        const quint32 secondPiece = ResolveObject(arguments.value(QStringLiteral("piece2")).toObject(), aliases);
        if (firstPiece == secondPiece)
        {
            throw std::invalid_argument("union_details requires two different pieces");
        }
        const QSet<quint32> beforePieces(m_window->pattern->DataPieces()->keyBegin(),
                                         m_window->pattern->DataPieces()->keyEnd());

        VToolUnionDetailsInitData initData;
        initData.d1id = firstPiece;
        initData.d2id = secondPiece;
        initData.indexD1 = static_cast<quint32>(arguments.value(QStringLiteral("edge_index1")).toInteger());
        initData.indexD2 = static_cast<quint32>(arguments.value(QStringLiteral("edge_index2")).toInteger());
        initData.retainPieces = arguments.value(QStringLiteral("retain_pieces")).toBool(false);
        initData.scene = m_window->m_sceneDetails;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;

        VAbstractApplication::VApp()->getUndoStack()->beginMacro(QStringLiteral("union details"));
        auto macroGuard = qScopeGuard([]() { VAbstractApplication::VApp()->getUndoStack()->endMacro(); });
        auto *unionTool = CreateToolFromCommand<VToolUnionDetails>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        if (unionTool == nullptr)
        {
            throw std::runtime_error("Valentina did not create the union tool");
        }

        QVector<quint32> newPieces;
        for (auto iterator = m_window->pattern->DataPieces()->constBegin();
             iterator != m_window->pattern->DataPieces()->constEnd(); ++iterator)
        {
            if (!beforePieces.contains(iterator.key()))
            {
                newPieces.append(iterator.key());
            }
        }
        std::sort(newPieces.begin(), newPieces.end());
        auto united = std::find_if(newPieces.constBegin(), newPieces.constEnd(), [this](quint32 id) {
            return m_window->pattern->GetPiece(id).IsUnited();
        });
        if (united == newPieces.constEnd())
        {
            throw std::runtime_error("Valentina union did not produce a united piece");
        }

        QJsonObject objects = aliases.value(QStringLiteral("objects")).toObject();
        QJsonArray deleted = summary.value(QStringLiteral("deleted")).toArray();
        for (auto iterator = objects.begin(); iterator != objects.end(); ++iterator)
        {
            QJsonObject record = iterator.value().toObject();
            const quint32 nativeId = static_cast<quint32>(record.value(QStringLiteral("native_id")).toInteger());
            if (!record.value(QStringLiteral("deleted")).toBool() &&
                (nativeId == firstPiece || nativeId == secondPiece))
            {
                record.insert(QStringLiteral("deleted"), true);
                iterator.value() = record;
                deleted.append(QJsonObject{{QStringLiteral("uuid"), iterator.key()},
                                           {QStringLiteral("alias"), record.value(QStringLiteral("alias"))}});
            }
        }
        aliases.insert(QStringLiteral("objects"), objects);
        summary.insert(QStringLiteral("deleted"), deleted);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Piece"), *united, aliases,
                       summary);

        if (initData.retainPieces)
        {
            QVector<quint32> retained;
            for (quint32 id : std::as_const(newPieces))
            {
                if (id != *united)
                {
                    retained.append(id);
                }
            }
            if (retained.size() != 2)
            {
                throw std::runtime_error("Valentina union did not retain exactly two source pieces");
            }
            RegisterObject(RequiredString(arguments, QStringLiteral("retained_alias1")), QStringLiteral("Piece"),
                           retained.at(0), aliases, summary);
            RegisterObject(RequiredString(arguments, QStringLiteral("retained_alias2")), QStringLiteral("Piece"),
                           retained.at(1), aliases, summary);
        }
        return;
    }

    if (action == QStringLiteral("pattern.true_darts"))
    {
        VToolTrueDartsInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.name1 = NativeObjectName(arguments, QStringLiteral("first_alias"),
                                         QStringLiteral("first_native_name"));
        initData.name2 = NativeObjectName(arguments, QStringLiteral("second_alias"),
                                         QStringLiteral("second_native_name"));
        initData.baseLineP1Id =
            ResolveObject(arguments.value(QStringLiteral("base_line_p1")).toObject(), aliases);
        initData.baseLineP2Id =
            ResolveObject(arguments.value(QStringLiteral("base_line_p2")).toObject(), aliases);
        initData.dartP1Id = ResolveObject(arguments.value(QStringLiteral("dart_p1")).toObject(), aliases);
        initData.dartP2Id = ResolveObject(arguments.value(QStringLiteral("dart_p2")).toObject(), aliases);
        initData.dartP3Id = ResolveObject(arguments.value(QStringLiteral("dart_p3")).toObject(), aliases);
        CreateToolFromCommand<VToolTrueDarts>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("first_alias")), QStringLiteral("TrueDartPoint"),
                       FindNativeObjectByName(initData.name1), aliases, summary);
        RegisterObject(RequiredString(arguments, QStringLiteral("second_alias")), QStringLiteral("TrueDartPoint"),
                       FindNativeObjectByName(initData.name2), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.p1Line = ResolveObject(arguments.value(QStringLiteral("line_p1")).toObject(), aliases);
        initData.p2Line = ResolveObject(arguments.value(QStringLiteral("line_p2")).toObject(), aliases);
        initData.pShoulder = ResolveObject(arguments.value(QStringLiteral("shoulder_point")).toObject(), aliases);
        initData.formula = arguments.contains(QStringLiteral("formula"))
                               ? RequiredString(arguments, QStringLiteral("formula"))
                               : NativeFormulaForMillimetres(
                                     arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        auto *tool = CreateToolFromCommand<VToolShoulderPoint>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("ShoulderPoint"),
                       tool->getId(), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        initData.formula = arguments.contains(QStringLiteral("formula"))
                               ? RequiredString(arguments, QStringLiteral("formula"))
                               : NativeFormulaForMillimetres(
                                     arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.angle = arguments.value(QStringLiteral("angle_deg")).toDouble();
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        auto *tool = CreateToolFromCommand<VToolNormal>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Normal"), tool->getId(),
                       aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("vertex")).toObject(), aliases);
        initData.thirdPointId = ResolveObject(arguments.value(QStringLiteral("third_point")).toObject(), aliases);
        initData.formula = arguments.contains(QStringLiteral("formula"))
                               ? RequiredString(arguments, QStringLiteral("formula"))
                               : NativeFormulaForMillimetres(
                                     arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        auto *tool = CreateToolFromCommand<VToolBisector>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Bisector"), tool->getId(),
                       aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.basePointId = ResolveObject(arguments.value(QStringLiteral("base_point")).toObject(), aliases);
        initData.p1LineId = ResolveObject(arguments.value(QStringLiteral("line_p1")).toObject(), aliases);
        initData.p2LineId = ResolveObject(arguments.value(QStringLiteral("line_p2")).toObject(), aliases);
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        auto *tool = CreateToolFromCommand<VToolHeight>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Height"), tool->getId(),
                       aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.axisP1Id = ResolveObject(arguments.value(QStringLiteral("axis_p1")).toObject(), aliases);
        initData.axisP2Id = ResolveObject(arguments.value(QStringLiteral("axis_p2")).toObject(), aliases);
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        auto *tool = CreateToolFromCommand<VToolTriangle>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("Triangle"), tool->getId(),
                       aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("first_point")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("second_point")).toObject(), aliases);
        auto *tool = CreateToolFromCommand<VToolPointOfIntersection>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("PointOfIntersection"),
                       tool->getId(), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.center = ResolveObject(arguments.value(QStringLiteral("center")).toObject(), aliases);
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("line_p1")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("line_p2")).toObject(), aliases);
        initData.radius = arguments.contains(QStringLiteral("formula_radius"))
                              ? RequiredString(arguments, QStringLiteral("formula_radius"))
                              : NativeFormulaForMillimetres(arguments.value(QStringLiteral("radius_mm")).toDouble());
        auto *tool = CreateToolFromCommand<VToolPointOfContact>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("PointOfContact"),
                       tool->getId(), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
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
        auto *tool = CreateToolFromCommand<VToolPointOfIntersectionCircles>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")),
                       QStringLiteral("PointOfIntersectionCircles"), tool->getId(), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.firstArcId = ResolveObject(arguments.value(QStringLiteral("first_arc")).toObject(), aliases);
        initData.secondArcId = ResolveObject(arguments.value(QStringLiteral("second_arc")).toObject(), aliases);
        initData.pType = CrossPoint(arguments);
        auto *tool = CreateToolFromCommand<VToolPointOfIntersectionArcs>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("PointOfIntersectionArcs"),
                       tool->getId(), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.firstCurveId = ResolveObject(arguments.value(QStringLiteral("first_curve")).toObject(), aliases);
        initData.secondCurveId =
            ResolveObject(arguments.value(QStringLiteral("second_curve")).toObject(), aliases);
        initData.vCrossPoint = VerticalCrossPoint(arguments);
        initData.hCrossPoint = HorizontalCrossPoint(arguments);
        auto *tool = CreateToolFromCommand<VToolPointOfIntersectionCurves>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")),
                       QStringLiteral("PointOfIntersectionCurves"), tool->getId(), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.circleCenterId = ResolveObject(arguments.value(QStringLiteral("center")).toObject(), aliases);
        initData.tangentPointId =
            ResolveObject(arguments.value(QStringLiteral("tangent_point")).toObject(), aliases);
        initData.circleRadius = arguments.contains(QStringLiteral("radius_formula"))
                                    ? RequiredString(arguments, QStringLiteral("radius_formula"))
                                    : NativeFormulaForMillimetres(
                                          arguments.value(QStringLiteral("radius_mm")).toDouble());
        initData.crossPoint = CrossPoint(arguments);
        auto *tool = CreateToolFromCommand<VToolPointFromCircleAndTangent>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")),
                       QStringLiteral("PointFromCircleAndTangent"), tool->getId(), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.arcId = ResolveObject(arguments.value(QStringLiteral("arc")).toObject(), aliases);
        initData.tangentPointId =
            ResolveObject(arguments.value(QStringLiteral("tangent_point")).toObject(), aliases);
        initData.crossPoint = CrossPoint(arguments);
        auto *tool = CreateToolFromCommand<VToolPointFromArcAndTangent>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("PointFromArcAndTangent"),
                       tool->getId(), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.basePointId = ResolveObject(arguments.value(QStringLiteral("base_point")).toObject(), aliases);
        initData.firstPointId = ResolveObject(arguments.value(QStringLiteral("line_p1")).toObject(), aliases);
        initData.secondPointId = ResolveObject(arguments.value(QStringLiteral("line_p2")).toObject(), aliases);
        initData.formulaAngle = arguments.contains(QStringLiteral("formula_angle"))
                                    ? RequiredString(arguments, QStringLiteral("formula_angle"))
                                    : QString::number(arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g', 15);
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        auto *tool = CreateToolFromCommand<VToolLineIntersectAxis>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("LineIntersectAxis"),
                       tool->getId(), aliases, summary);
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
        initData.name = NativeObjectName(arguments);
        initData.basePointId = ResolveObject(arguments.value(QStringLiteral("base_point")).toObject(), aliases);
        initData.curveId = ResolveObject(arguments.value(QStringLiteral("curve")).toObject(), aliases);
        initData.formulaAngle = arguments.contains(QStringLiteral("formula_angle"))
                                    ? RequiredString(arguments, QStringLiteral("formula_angle"))
                                    : QString::number(arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g', 15);
        initData.typeLine = arguments.value(QStringLiteral("line_type")).toString(TypeLineLine);
        initData.lineColor = CanonicalToolColor(arguments.value(QStringLiteral("line_color")).toString(ColorBlack));
        auto *tool = CreateToolFromCommand<VToolCurveIntersectAxis>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), QStringLiteral("CurveIntersectAxis"),
                       tool->getId(), aliases, summary);
        return;
    }

    if (action == QStringLiteral("pattern.rotation"))
    {
        const QJsonArray items = arguments.value(QStringLiteral("objects")).toArray();
        VToolRotationInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.origin = ResolveObject(arguments.value(QStringLiteral("origin")).toObject(), aliases);
        initData.angle = arguments.contains(QStringLiteral("formula_angle"))
                             ? RequiredString(arguments, QStringLiteral("formula_angle"))
                             : QString::number(arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g', 15);
        initData.source = operationSources(items);
        CreateToolFromCommand<VToolRotation>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        registerDestinations(items, initData.destination, QStringLiteral("RotatedObject"));
        return;
    }

    if (action == QStringLiteral("pattern.move"))
    {
        const QJsonArray items = arguments.value(QStringLiteral("objects")).toArray();
        VToolMoveInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.rotationOrigin =
            ResolveObject(arguments.value(QStringLiteral("rotation_origin")).toObject(), aliases);
        initData.formulaLength = arguments.contains(QStringLiteral("formula_length"))
                                     ? RequiredString(arguments, QStringLiteral("formula_length"))
                                     : NativeFormulaForMillimetres(
                                           arguments.value(QStringLiteral("length_mm")).toDouble());
        initData.formulaAngle = arguments.contains(QStringLiteral("formula_angle"))
                                    ? RequiredString(arguments, QStringLiteral("formula_angle"))
                                    : QString::number(
                                          arguments.value(QStringLiteral("angle_deg")).toDouble(), 'g', 15);
        initData.formulaRotationAngle = arguments.contains(QStringLiteral("formula_rotation_angle"))
                                            ? RequiredString(arguments, QStringLiteral("formula_rotation_angle"))
                                            : QString::number(
                                                  arguments.value(QStringLiteral("rotation_angle_deg")).toDouble(),
                                                  'g', 15);
        initData.source = operationSources(items);
        CreateToolFromCommand<VToolMove>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        registerDestinations(items, initData.destination, QStringLiteral("MovedObject"));
        return;
    }

    if (action == QStringLiteral("pattern.flipping_by_line"))
    {
        const QJsonArray items = arguments.value(QStringLiteral("objects")).toArray();
        VToolFlippingByLineInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.firstLinePointId =
            ResolveObject(arguments.value(QStringLiteral("line_p1")).toObject(), aliases);
        initData.secondLinePointId =
            ResolveObject(arguments.value(QStringLiteral("line_p2")).toObject(), aliases);
        initData.source = operationSources(items);
        CreateToolFromCommand<VToolFlippingByLine>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        for (qsizetype index = 0; index < items.size(); ++index)
        {
            RegisterObject(RequiredString(items.at(index).toObject(), QStringLiteral("alias")),
                           QStringLiteral("FlippedObject"), FindNativeObjectByName(initData.source.at(index).name),
                           aliases, summary);
        }
        return;
    }

    if (action == QStringLiteral("pattern.flipping_by_axis"))
    {
        const QJsonArray items = arguments.value(QStringLiteral("objects")).toArray();
        VToolFlippingByAxisInitData initData;
        initData.scene = m_window->m_sceneDraw;
        initData.doc = m_window->doc;
        initData.data = m_window->pattern;
        initData.parse = Document::FullParse;
        initData.typeCreation = Source::FromGui;
        initData.originPointId = ResolveObject(arguments.value(QStringLiteral("origin")).toObject(), aliases);
        const QString axis = arguments.value(QStringLiteral("axis")).toString(QStringLiteral("vertical"));
        if (axis != QStringLiteral("vertical") && axis != QStringLiteral("horizontal"))
        {
            throw std::invalid_argument("axis must be vertical or horizontal");
        }
        initData.axisType =
            axis == QStringLiteral("vertical") ? AxisType::VerticalAxis : AxisType::HorizontalAxis;
        initData.source = operationSources(items);
        CreateToolFromCommand<VToolFlippingByAxis>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
        for (qsizetype index = 0; index < items.size(); ++index)
        {
            RegisterObject(RequiredString(items.at(index).toObject(), QStringLiteral("alias")),
                           QStringLiteral("FlippedObject"), FindNativeObjectByName(initData.source.at(index).name),
                           aliases, summary);
        }
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
        initData.name = NativeObjectName(arguments);
        initData.baseCurveId = ResolveObject(arguments.value(QStringLiteral("curve")).toObject(), aliases);
        initData.formula = arguments.contains(QStringLiteral("formula_length"))
                               ? RequiredString(arguments, QStringLiteral("formula_length"))
                               : NativeFormulaForMillimetres(
                                     arguments.value(QStringLiteral("length_mm")).toDouble());

        VToolSinglePoint *tool = nullptr;
        QString type;
        if (action == QStringLiteral("pattern.cut_arc"))
        {
            tool = CreateToolFromCommand<VToolCutArc>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
            type = QStringLiteral("CutArc");
        }
        else if (action == QStringLiteral("pattern.cut_spline"))
        {
            tool = CreateToolFromCommand<VToolCutSpline>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
            type = QStringLiteral("CutSpline");
        }
        else
        {
            tool = CreateToolFromCommand<VToolCutSplinePath>(initData, m_window->m_sceneDraw, m_window->doc, m_window->pattern);
            type = QStringLiteral("CutSplinePath");
        }
        RegisterObject(RequiredString(arguments, QStringLiteral("alias")), type, tool->getId(), aliases, summary);
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
auto VCommandService::FindNativeObjectByName(const QString &name) const -> quint32
{
    QList<quint32> matches;
    const auto *objects = m_window->pattern->CalculationGObjects();
    for (auto iterator = objects->constBegin(); iterator != objects->constEnd(); ++iterator)
    {
        if (iterator.value() && iterator.value()->name() == name)
        {
            matches.append(iterator.key());
        }
    }
    if (matches.size() != 1)
    {
        throw std::invalid_argument(
            QStringLiteral("Expected one native object named %1, found %2").arg(name).arg(matches.size()).toStdString());
    }
    return matches.constFirst();
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
