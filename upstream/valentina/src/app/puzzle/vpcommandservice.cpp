/************************************************************************
 ** GarmentCAD command bridge for Puzzle.
 ** This file is distributed under the same GPL-3.0-or-later terms as Puzzle.
 *************************************************************************/
#include "vpcommandservice.h"

#include "layout/vplayout.h"
#include "layout/vplayoutsettings.h"
#include "layout/vppiece.h"
#include "layout/vpsheet.h"
#include "undocommands/vpundoaddsheet.h"
#include "undocommands/vpundomovepieceonsheet.h"
#include "undocommands/vpundopiecemove.h"
#include "undocommands/vpundopiecerotate.h"
#include "vpmainwindow.h"

#include "../vmisc/def.h"
#include "../vmisc/vsysexits.h"
#include "../vlayout/vlayoutgenerator.h"

#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSaveFile>
#include <QTextStream>
#include <QUndoStack>

#include <stdexcept>

using namespace Qt::Literals::StringLiterals;

namespace
{
auto RequiredString(const QJsonObject &object, const QString &name) -> QString
{
    const QString value = object.value(name).toString();
    if (value.isEmpty())
    {
        throw std::invalid_argument(QStringLiteral("%1 is required").arg(name).toStdString());
    }
    return value;
}

auto MmToPx(qreal value) -> qreal
{
    return UnitConvertor(value, Unit::Mm, Unit::Px);
}

auto ObjectReference(const QString &uuid, const QString &alias) -> QJsonObject
{
    return {{QStringLiteral("uuid"), uuid}, {QStringLiteral("alias"), alias}};
}

void AddReference(QJsonObject &summary, const QString &bucket, const QJsonObject &reference)
{
    QJsonArray values = summary.value(bucket).toArray();
    values.append(reference);
    summary.insert(bucket, values);
}
} // namespace

VPCommandService::VPCommandService(VPMainWindow *window)
  : m_window(window)
{
    if (m_window == nullptr)
    {
        throw std::invalid_argument("VPCommandService requires a VPMainWindow");
    }
}

auto VPCommandService::RunOnce() -> int
{
    QTextStream input(stdin, QIODevice::ReadOnly);
    QTextStream output(stdout, QIODevice::WriteOnly);
    const QJsonDocument document = QJsonDocument::fromJson(input.readAll().toUtf8());
    QJsonObject response;
    try
    {
        if (!document.isObject())
        {
            throw std::invalid_argument("Puzzle command request must be a JSON object");
        }
        response = Dispatch(document.object());
        response.insert(QStringLiteral("ok"), true);
    }
    catch (const std::exception &error)
    {
        response = {{QStringLiteral("ok"), false},
                    {QStringLiteral("error"),
                     QJsonObject{{QStringLiteral("code"), QStringLiteral("puzzle_error")},
                                 {QStringLiteral("message"), QString::fromUtf8(error.what())}}}};
    }
    output << QJsonDocument(response).toJson(QJsonDocument::Compact);
    output.flush();
    return response.value(QStringLiteral("ok")).toBool() ? V_EX_OK : V_EX_DATAERR;
}

auto VPCommandService::Dispatch(const QJsonObject &request) -> QJsonObject
{
    const QString method = RequiredString(request, QStringLiteral("method"));
    if (method == QStringLiteral("service.info"))
    {
        return {{QStringLiteral("application"), QStringLiteral("Puzzle")},
                {QStringLiteral("protocol_version"), QStringLiteral("1.0")},
                {QStringLiteral("units"), QStringLiteral("mm")},
                {QStringLiteral("preview_commit"), true},
                {QStringLiteral("handlers"),
                 QJsonArray{QStringLiteral("layout.generate"), QStringLiteral("layout.sheet_add"),
                            QStringLiteral("layout.sheet_update"), QStringLiteral("layout.move_piece"),
                            QStringLiteral("layout.place"), QStringLiteral("layout.rotate_piece"),
                            QStringLiteral("layout.flip_piece"), QStringLiteral("layout.settings_update"),
                            QStringLiteral("layout.print"), QStringLiteral("export.layout")}}};
    }
    if (method == QStringLiteral("commands.preview"))
    {
        return Preview(request);
    }
    if (method == QStringLiteral("commands.commit"))
    {
        return Commit(request);
    }
    throw std::invalid_argument("Unknown Puzzle command method");
}

auto VPCommandService::Preview(const QJsonObject &request) -> QJsonObject
{
    const QString projectRoot = QFileInfo(RequiredString(request, QStringLiteral("project_root"))).absoluteFilePath();
    const QString changeSetId = RequiredString(request, QStringLiteral("change_set_id"));
    ValidateChangeSetId(changeSetId);
    m_candidateRoot = CandidateRoot(projectRoot, changeSetId);
    m_candidateLayout = QDir(m_candidateRoot).filePath(QStringLiteral("layout/main.vlt"));
    QDir().mkpath(QFileInfo(m_candidateLayout).absolutePath());

    CopyDirectoryFiles(QDir(projectRoot).filePath(QStringLiteral("layout")),
                       QDir(m_candidateRoot).filePath(QStringLiteral("layout")));
    if (QFileInfo::exists(m_candidateLayout) && !m_window->LoadFile(m_candidateLayout))
    {
        throw std::runtime_error("Puzzle could not open the staged layout");
    }

    QJsonObject summary{{QStringLiteral("created"), QJsonArray{}},
                        {QStringLiteral("changed"), QJsonArray{}},
                        {QStringLiteral("deleted"), QJsonArray{}},
                        {QStringLiteral("measurements"), QJsonObject{}},
                        {QStringLiteral("issues"), QJsonArray{}}};
    const QJsonArray operations = request.value(QStringLiteral("operations")).toArray();
    for (const QJsonValue value : operations)
    {
        ApplyOperation(value.toObject(), summary);
    }
    QString error;
    if (!m_window->SaveLayout(m_candidateLayout, error))
    {
        throw std::runtime_error(QStringLiteral("Unable to save staged Puzzle layout: %1").arg(error).toStdString());
    }
    return {{QStringLiteral("change_set_id"), changeSetId}, {QStringLiteral("summary"), summary}};
}

auto VPCommandService::Commit(const QJsonObject &request) -> QJsonObject
{
    const QString projectRoot = QFileInfo(RequiredString(request, QStringLiteral("project_root"))).absoluteFilePath();
    const QString changeSetId = RequiredString(request, QStringLiteral("change_set_id"));
    ValidateChangeSetId(changeSetId);
    const QString candidate = CandidateRoot(projectRoot, changeSetId);
    const QString layout = QDir(candidate).filePath(QStringLiteral("layout/main.vlt"));
    if (!QFileInfo::exists(layout))
    {
        throw std::invalid_argument("Puzzle preview does not exist");
    }
    CopyDirectoryFiles(QDir(candidate).filePath(QStringLiteral("layout")),
                       QDir(projectRoot).filePath(QStringLiteral("layout")));
    return {{QStringLiteral("change_set_id"), changeSetId}};
}

void VPCommandService::ApplyOperation(const QJsonObject &operation, QJsonObject &summary)
{
    const QString action = RequiredString(operation, QStringLiteral("action"));
    const QJsonObject arguments = operation.value(QStringLiteral("arguments")).toObject();
    VPLayoutPtr layout = m_window->m_layout;

    if (action == QStringLiteral("layout.generate"))
    {
        const QString source = arguments.value(QStringLiteral("raw_layout_path")).toString();
        if (!source.isEmpty())
        {
            if (!QFileInfo::exists(source) || !m_window->ImportRawLayout(source))
            {
                throw std::invalid_argument("Unable to import the requested native raw layout");
            }
        }
        if (arguments.contains(QStringLiteral("sheet_width_mm")) || arguments.contains(QStringLiteral("sheet_height_mm")))
        {
            VPSheetPtr sheet = layout->GetFocusedSheet();
            const QSizeF current = sheet->GetSheetSize();
            sheet->SetSheetSize(arguments.contains(QStringLiteral("sheet_width_mm"))
                                    ? MmToPx(arguments.value(QStringLiteral("sheet_width_mm")).toDouble())
                                    : current.width(),
                                arguments.contains(QStringLiteral("sheet_height_mm"))
                                    ? MmToPx(arguments.value(QStringLiteral("sheet_height_mm")).toDouble())
                                    : current.height());
        }
        if (arguments.value(QStringLiteral("auto_arrange")).toBool(true) && !layout->GetPieces().isEmpty())
        {
            QVector<VLayoutPiece> details;
            details.reserve(layout->GetPieces().size());
            for (const VPPiecePtr &piece : layout->GetPieces())
            {
                details.append(*piece);
            }

            const VPSheetPtr focused = layout->GetFocusedSheet();
            const qreal paperWidth = arguments.contains(QStringLiteral("sheet_width_mm"))
                                         ? MmToPx(arguments.value(QStringLiteral("sheet_width_mm")).toDouble())
                                         : focused->GetSheetSize().width();
            const qreal paperHeight = arguments.contains(QStringLiteral("sheet_height_mm"))
                                          ? MmToPx(arguments.value(QStringLiteral("sheet_height_mm")).toDouble())
                                          : focused->GetSheetSize().height();
            VLayoutGenerator generator;
            generator.SetDetails(details);
            generator.SetPaperWidth(paperWidth);
            generator.SetPaperHeight(paperHeight);
            generator.SetLayoutWidth(MmToPx(arguments.value(QStringLiteral("piece_gap_mm")).toDouble(
                UnitConvertor(layout->LayoutSettings().GetPiecesGap(), Unit::Px, Unit::Mm))));
            generator.SetRotate(arguments.value(QStringLiteral("allow_rotation")).toBool(true));
            generator.SetRotationNumber(arguments.value(QStringLiteral("rotation_count")).toInt(8));
            generator.SetFollowGrainline(arguments.value(QStringLiteral("follow_grainline")).toBool(
                layout->LayoutSettings().GetFollowGrainline()));
            generator.SetNestQuantity(true);
            generator.SetPreferOneSheetSolution(arguments.value(QStringLiteral("prefer_one_sheet")).toBool(true));
            generator.SetAutoCropLength(arguments.value(QStringLiteral("auto_crop_length")).toBool(false));
            generator.SetAutoCropWidth(arguments.value(QStringLiteral("auto_crop_width")).toBool(false));
            generator.SetShift(-1);

            QElapsedTimer timer;
            timer.start();
            const int timeout = qBound(1000, arguments.value(QStringLiteral("timeout_ms")).toInt(5000), 60000);
            generator.Generate(timer, timeout);
            if (generator.State() != LayoutErrors::NoError || generator.PapersCount() == 0)
            {
                throw std::runtime_error(
                    QStringLiteral("Native layout generation failed with state %1")
                        .arg(static_cast<int>(generator.State())).toStdString());
            }

            const VPLayoutSettings settings = layout->LayoutSettings();
            layout->Clear();
            layout->LayoutSettings() = settings;
            layout->AddTrashSheet(VPSheetPtr(new VPSheet(layout)));
            QHash<QString, int> copyNumbers;
            const QVector<QVector<VLayoutPiece>> pages = generator.GetAllDetails();
            for (int pageIndex = 0; pageIndex < pages.size(); ++pageIndex)
            {
                VPSheetPtr sheet(new VPSheet(layout));
                sheet->SetName(QStringLiteral("Sheet %1").arg(pageIndex + 1));
                sheet->SetSheetSize(paperWidth, paperHeight);
                layout->AddSheet(sheet);
                for (const VLayoutPiece &detail : pages.at(pageIndex))
                {
                    VPPiecePtr piece(new VPPiece(detail));
                    const QString baseId = detail.GetUniqueID();
                    piece->SetCopyNumber(static_cast<quint16>(++copyNumbers[baseId]));
                    piece->SetMatrix(detail.GetMatrix());
                    piece->SetVerticallyFlipped(detail.IsVerticallyFlipped());
                    piece->SetHorizontallyFlipped(detail.IsHorizontallyFlipped());
                    piece->SetSheet(sheet);
                    VPLayout::AddPiece(layout, piece);
                }
            }
            layout->SetFocusedSheet();
            layout->CheckPiecesPositionValidity();
            QJsonObject values = summary.value(QStringLiteral("measurements")).toObject();
            values.insert(QStringLiteral("layout.efficiency"), generator.LayoutEfficiency());
            values.insert(QStringLiteral("layout.sheets"), generator.PapersCount());
            summary.insert(QStringLiteral("measurements"), values);
        }
        AddReference(summary, QStringLiteral("changed"),
                     ObjectReference(layout->Uuid().toString(QUuid::WithoutBraces), QStringLiteral("layout.main")));
        return;
    }

    if (action == QStringLiteral("layout.sheet_add"))
    {
        VPSheetPtr sheet(new VPSheet(layout));
        sheet->SetName(arguments.value(QStringLiteral("name")).toString(
            QStringLiteral("Sheet %1").arg(layout->GetAllSheets().size() + 1)));
        sheet->SetSheetSize(MmToPx(arguments.value(QStringLiteral("width_mm")).toDouble(841)),
                            MmToPx(arguments.value(QStringLiteral("height_mm")).toDouble(1189)));
        sheet->SetSheetMargins(
            MmToPx(arguments.value(QStringLiteral("margin_left_mm")).toDouble(0)),
            MmToPx(arguments.value(QStringLiteral("margin_top_mm")).toDouble(0)),
            MmToPx(arguments.value(QStringLiteral("margin_right_mm")).toDouble(0)),
            MmToPx(arguments.value(QStringLiteral("margin_bottom_mm")).toDouble(0)));
        layout->UndoStack()->push(new VPUndoAddSheet(sheet));
        AddReference(summary, QStringLiteral("created"),
                     ObjectReference(sheet->Uuid().toString(QUuid::WithoutBraces), sheet->GetName()));
        return;
    }

    if (action == QStringLiteral("layout.sheet_update"))
    {
        VPSheetPtr sheet = ResolveSheet(arguments);
        const QSizeF size = sheet->GetSheetSize();
        sheet->SetSheetSize(arguments.contains(QStringLiteral("width_mm"))
                                ? MmToPx(arguments.value(QStringLiteral("width_mm")).toDouble())
                                : size.width(),
                            arguments.contains(QStringLiteral("height_mm"))
                                ? MmToPx(arguments.value(QStringLiteral("height_mm")).toDouble())
                                : size.height());
        const QMarginsF margins = sheet->GetSheetMargins();
        sheet->SetSheetMargins(arguments.contains(QStringLiteral("margin_left_mm"))
                                  ? MmToPx(arguments.value(QStringLiteral("margin_left_mm")).toDouble())
                                  : margins.left(),
                              arguments.contains(QStringLiteral("margin_top_mm"))
                                  ? MmToPx(arguments.value(QStringLiteral("margin_top_mm")).toDouble())
                                  : margins.top(),
                              arguments.contains(QStringLiteral("margin_right_mm"))
                                  ? MmToPx(arguments.value(QStringLiteral("margin_right_mm")).toDouble())
                                  : margins.right(),
                              arguments.contains(QStringLiteral("margin_bottom_mm"))
                                  ? MmToPx(arguments.value(QStringLiteral("margin_bottom_mm")).toDouble())
                                  : margins.bottom());
        if (arguments.contains(QStringLiteral("name")))
        {
            sheet->SetName(arguments.value(QStringLiteral("name")).toString());
        }
        if (arguments.contains(QStringLiteral("ignore_margins")))
        {
            sheet->SetIgnoreMargins(arguments.value(QStringLiteral("ignore_margins")).toBool());
        }
        AddReference(summary, QStringLiteral("changed"),
                     ObjectReference(sheet->Uuid().toString(QUuid::WithoutBraces), sheet->GetName()));
        return;
    }

    if (action == QStringLiteral("layout.settings_update"))
    {
        VPLayoutSettings &settings = layout->LayoutSettings();
        if (arguments.contains(QStringLiteral("title"))) settings.SetTitle(arguments.value(QStringLiteral("title")).toString());
        if (arguments.contains(QStringLiteral("description"))) settings.SetDescription(arguments.value(QStringLiteral("description")).toString());
        if (arguments.contains(QStringLiteral("piece_gap_mm"))) settings.SetPiecesGap(MmToPx(arguments.value(QStringLiteral("piece_gap_mm")).toDouble()));
        if (arguments.contains(QStringLiteral("sticky_edges"))) settings.SetStickyEdges(arguments.value(QStringLiteral("sticky_edges")).toBool());
        if (arguments.contains(QStringLiteral("follow_grainline"))) settings.SetFollowGrainline(arguments.value(QStringLiteral("follow_grainline")).toBool());
        if (arguments.contains(QStringLiteral("boundary_with_notches"))) settings.SetBoundaryTogetherWithNotches(arguments.value(QStringLiteral("boundary_with_notches")).toBool());
        if (arguments.contains(QStringLiteral("cut_on_fold"))) settings.SetCutOnFold(arguments.value(QStringLiteral("cut_on_fold")).toBool());
        if (arguments.contains(QStringLiteral("horizontal_scale"))) settings.SetHorizontalScale(arguments.value(QStringLiteral("horizontal_scale")).toDouble());
        if (arguments.contains(QStringLiteral("vertical_scale"))) settings.SetVerticalScale(arguments.value(QStringLiteral("vertical_scale")).toDouble());
        AddReference(summary, QStringLiteral("changed"),
                     ObjectReference(layout->Uuid().toString(QUuid::WithoutBraces), QStringLiteral("layout.settings")));
        return;
    }

    if (action == QStringLiteral("layout.place") || action == QStringLiteral("layout.move_piece"))
    {
        VPPiecePtr piece = ResolvePiece(arguments);
        if (action == QStringLiteral("layout.place"))
        {
            VPSheetPtr sheet = ResolveSheet(arguments);
            if (piece->Sheet() != sheet)
            {
                layout->UndoStack()->push(new VPUndoMovePieceOnSheet(sheet, piece));
            }
        }
        qreal dx = MmToPx(arguments.value(QStringLiteral("dx_mm")).toDouble());
        qreal dy = MmToPx(arguments.value(QStringLiteral("dy_mm")).toDouble());
        if (action == QStringLiteral("layout.place"))
        {
            const QPointF current = piece->GetPosition();
            dx = MmToPx(arguments.value(QStringLiteral("x_mm")).toDouble()) - current.x();
            dy = MmToPx(arguments.value(QStringLiteral("y_mm")).toDouble()) - current.y();
        }
        layout->UndoStack()->push(new VPUndoPieceMove(piece, dx, dy));
        AddReference(summary, QStringLiteral("changed"),
                     ObjectReference(piece->GetUniqueID(), piece->GetName()));
        return;
    }

    if (action == QStringLiteral("layout.rotate_piece"))
    {
        VPPiecePtr piece = ResolvePiece(arguments);
        layout->UndoStack()->push(new VPUndoPieceRotate(
            piece, {.origin = piece->MappedDetailBoundingRect().center(), .custom = true},
            arguments.value(QStringLiteral("angle_deg")).toDouble()));
        AddReference(summary, QStringLiteral("changed"), ObjectReference(piece->GetUniqueID(), piece->GetName()));
        return;
    }

    if (action == QStringLiteral("layout.flip_piece"))
    {
        VPPiecePtr piece = ResolvePiece(arguments);
        const QString axis = arguments.value(QStringLiteral("axis")).toString(QStringLiteral("vertical"));
        if (axis == QStringLiteral("vertical")) piece->FlipVertically();
        else if (axis == QStringLiteral("horizontal")) piece->FlipHorizontally();
        else throw std::invalid_argument("Flip axis must be vertical or horizontal");
        AddReference(summary, QStringLiteral("changed"), ObjectReference(piece->GetUniqueID(), piece->GetName()));
        return;
    }

    if (action == QStringLiteral("layout.print") || action == QStringLiteral("export.layout"))
    {
        const QString format = action == QStringLiteral("layout.print")
                                   ? QStringLiteral("pdf_tiled")
                                   : arguments.value(QStringLiteral("format")).toString(QStringLiteral("pdf"));
        const QString output = arguments.value(QStringLiteral("output_path")).toString(
            QStringLiteral("artifacts/exports/layout"));
        const QString absolute = QDir(m_candidateRoot).filePath(output);
        const QString allowed = QFileInfo(m_candidateRoot).absoluteFilePath() + QLatin1Char('/');
        if (!QFileInfo(absolute).absoluteFilePath().startsWith(allowed))
        {
            throw std::invalid_argument("Layout export path must stay inside the preview project");
        }
        QString error;
        if (!m_window->ExportForCommand(format, absolute, arguments, error))
        {
            throw std::runtime_error(QStringLiteral("Puzzle export failed: %1").arg(error).toStdString());
        }
        AddReference(summary, QStringLiteral("created"), ObjectReference({}, output));
        return;
    }

    throw std::invalid_argument(QStringLiteral("Unsupported Puzzle action: %1").arg(action).toStdString());
}

auto VPCommandService::ResolveSheet(const QJsonObject &arguments) const -> VPSheetPtr
{
    const QString uuid = arguments.value(QStringLiteral("sheet_uuid")).toString();
    const QString name = arguments.value(QStringLiteral("sheet")).toString();
    const int index = arguments.value(QStringLiteral("sheet_index")).toInt(-1);
    const QList<VPSheetPtr> sheets = m_window->m_layout->GetAllSheets();
    QList<VPSheetPtr> matches;
    for (const VPSheetPtr &sheet : sheets)
    {
        if ((!uuid.isEmpty() && sheet->Uuid().toString(QUuid::WithoutBraces) == uuid) ||
            (!name.isEmpty() && sheet->GetName() == name))
        {
            matches.append(sheet);
        }
    }
    if (matches.size() > 1) throw std::invalid_argument("Sheet reference is ambiguous");
    if (matches.size() == 1) return matches.constFirst();
    if (index >= 0 && index < sheets.size()) return sheets.at(index);
    if (uuid.isEmpty() && name.isEmpty() && index < 0 && !m_window->m_layout->GetFocusedSheet().isNull())
        return m_window->m_layout->GetFocusedSheet();
    throw std::invalid_argument("Unknown Puzzle sheet reference");
}

auto VPCommandService::ResolvePiece(const QJsonObject &arguments) const -> VPPiecePtr
{
    const QString id = arguments.value(QStringLiteral("piece_id")).toString();
    const QString name = arguments.value(QStringLiteral("piece")).toString();
    const int copy = arguments.value(QStringLiteral("copy_number")).toInt(0);
    QList<VPPiecePtr> matches;
    for (const VPPiecePtr &piece : m_window->m_layout->GetPieces())
    {
        if ((!id.isEmpty() && piece->GetUniqueID() == id) ||
            (!name.isEmpty() && piece->GetName() == name && (copy == 0 || piece->CopyNumber() == copy)))
            matches.append(piece);
    }
    if (matches.size() > 1) throw std::invalid_argument("Piece reference is ambiguous; pass piece_id or copy_number");
    if (matches.size() == 1) return matches.constFirst();
    throw std::invalid_argument("Unknown Puzzle piece reference");
}

auto VPCommandService::CandidateRoot(const QString &projectRoot, const QString &changeSetId) -> QString
{
    return QDir(projectRoot).filePath(QStringLiteral(".garmentcad/changesets/%1").arg(changeSetId));
}

void VPCommandService::ValidateChangeSetId(const QString &changeSetId)
{
    if (changeSetId.isEmpty() || changeSetId.contains(QLatin1Char('/')) || changeSetId.contains(QLatin1Char('\\')) ||
        changeSetId == QStringLiteral(".") || changeSetId == QStringLiteral(".."))
        throw std::invalid_argument("Invalid change_set_id");
}

void VPCommandService::AtomicCopy(const QString &source, const QString &destination)
{
    QDir().mkpath(QFileInfo(destination).absolutePath());
    QFile input(source);
    if (!input.open(QIODevice::ReadOnly)) throw std::runtime_error("Unable to read staged Puzzle file");
    QSaveFile output(destination);
    if (!output.open(QIODevice::WriteOnly) || output.write(input.readAll()) < 0 || !output.commit())
        throw std::runtime_error("Unable to atomically copy Puzzle file");
}

void VPCommandService::CopyDirectoryFiles(const QString &sourcePath, const QString &destinationPath)
{
    const QDir source(sourcePath);
    if (!source.exists()) return;
    QDir().mkpath(destinationPath);
    for (const QFileInfo &entry : source.entryInfoList(QDir::Files | QDir::Dirs | QDir::NoDotAndDotDot))
    {
        const QString destination = QDir(destinationPath).filePath(entry.fileName());
        if (entry.isDir()) CopyDirectoryFiles(entry.absoluteFilePath(), destination);
        else AtomicCopy(entry.absoluteFilePath(), destination);
    }
}
