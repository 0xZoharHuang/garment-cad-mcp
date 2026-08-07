/************************************************************************
 **
 **  Agent-safe JSON command boundary for garment-cad-mcp.
 **  Copyright (C) 2026 garment-cad-mcp contributors.
 **
 **  This file is distributed under the same GPL-3.0-or-later terms as
 **  Valentina.  It deliberately delegates construction to native tools.
 **
 *************************************************************************/

#ifndef VCOMMANDSERVICE_H
#define VCOMMANDSERVICE_H

#include <QJsonArray>
#include <QJsonObject>
#include <QString>

class MainWindow;

class VCommandService final
{
public:
    explicit VCommandService(MainWindow *window);

    auto RunOnce() -> int;

private:
    MainWindow *m_window;
    QString m_candidateRoot{};
    QString m_candidatePattern{};

    auto Dispatch(const QJsonObject &request) -> QJsonObject;
    auto Preview(const QJsonObject &request) -> QJsonObject;
    auto Commit(const QJsonObject &request) -> QJsonObject;
    auto Snapshot(const QJsonObject &request) -> QJsonObject;
    auto ApplyOperation(const QJsonObject &operation, QJsonObject &aliases, QJsonObject &summary) -> void;
    auto ResolveObject(const QJsonObject &reference, const QJsonObject &aliases) const -> quint32;
    auto FindNativeObjectByName(const QString &name) const -> quint32;
    auto RegisterObject(const QString &alias, const QString &kind, quint32 nativeId, QJsonObject &aliases,
                        QJsonObject &summary) const -> void;

    static auto CandidateRoot(const QString &projectRoot, const QString &changeSetId) -> QString;
    static auto ValidateChangeSetId(const QString &changeSetId) -> void;
    static auto ReadJsonFile(const QString &path) -> QJsonObject;
    static auto WriteJsonFile(const QString &path, const QJsonObject &object) -> void;
    static auto AtomicCopy(const QString &source, const QString &destination) -> void;
    static auto AddIssue(QJsonObject &summary, const QString &severity, const QString &code,
                         const QString &message) -> void;
};

#endif // VCOMMANDSERVICE_H
