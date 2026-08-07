/************************************************************************
 ** GarmentCAD command bridge for Puzzle.
 ** This file is distributed under the same GPL-3.0-or-later terms as Puzzle.
 *************************************************************************/
#ifndef VPCOMMANDSERVICE_H
#define VPCOMMANDSERVICE_H

#include <QJsonObject>
#include <QString>

class VPMainWindow;
class VPPiece;
class VPSheet;
template <typename T> class QSharedPointer;

class VPCommandService final
{
public:
    explicit VPCommandService(VPMainWindow *window);
    auto RunOnce() -> int;

private:
    VPMainWindow *m_window;
    QString m_candidateRoot{};
    QString m_candidateLayout{};

    auto Dispatch(const QJsonObject &request) -> QJsonObject;
    auto Preview(const QJsonObject &request) -> QJsonObject;
    auto Commit(const QJsonObject &request) -> QJsonObject;
    void ApplyOperation(const QJsonObject &operation, QJsonObject &summary);

    auto ResolveSheet(const QJsonObject &arguments) const -> QSharedPointer<VPSheet>;
    auto ResolvePiece(const QJsonObject &arguments) const -> QSharedPointer<VPPiece>;

    static auto CandidateRoot(const QString &projectRoot, const QString &changeSetId) -> QString;
    static void ValidateChangeSetId(const QString &changeSetId);
    static void AtomicCopy(const QString &source, const QString &destination);
    static void CopyDirectoryFiles(const QString &source, const QString &destination);
};

#endif // VPCOMMANDSERVICE_H
