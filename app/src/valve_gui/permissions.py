ROLE_DEVELOPER = "developer"
ROLE_MANAGER = "manager"
ROLE_OPERATOR = "operator"

ROLE_LABELS = {
    ROLE_DEVELOPER: "開發者",
    ROLE_MANAGER: "管理者",
    ROLE_OPERATOR: "作業員",
}

ROLE_OPTIONS = [
    (ROLE_OPERATOR, ROLE_LABELS[ROLE_OPERATOR]),
    (ROLE_MANAGER, ROLE_LABELS[ROLE_MANAGER]),
    (ROLE_DEVELOPER, ROLE_LABELS[ROLE_DEVELOPER]),
]

DEFAULT_ROLE_PASSWORDS = {
    ROLE_DEVELOPER: "0000",
    ROLE_MANAGER: "1234",
    ROLE_OPERATOR: "",
}

PERMISSION_OPEN_SETTINGS = "open_settings"
PERMISSION_OPEN_MONITOR = "open_monitor"
PERMISSION_OPEN_HISTORY = "open_history"
PERMISSION_MANAGE_MODELS = "manage_models"
PERMISSION_EXPORT_RECORDS = "export_records"
PERMISSION_VIEW_ALL_RECORDS = "view_all_records"
PERMISSION_VIEW_SESSIONS = "view_sessions"
PERMISSION_USE_SIMULATION = "use_simulation"
PERMISSION_QC_VIEW = "qc_view"
PERMISSION_QC_PRODUCT_MANAGE = "qc_product_manage"

PERMISSION_LABELS = {
    PERMISSION_OPEN_SETTINGS: "進入相機設定",
    PERMISSION_OPEN_MONITOR: "進入監視頁面",
    PERMISSION_OPEN_HISTORY: "查看歷史紀錄",
    PERMISSION_MANAGE_MODELS: "管理模型",
    PERMISSION_EXPORT_RECORDS: "匯出紀錄",
    PERMISSION_VIEW_ALL_RECORDS: "查看全部檢測紀錄",
    PERMISSION_VIEW_SESSIONS: "查看登入紀錄",
    PERMISSION_USE_SIMULATION: "使用模擬相機",
    PERMISSION_QC_VIEW: "查看品管統計",
    PERMISSION_QC_PRODUCT_MANAGE: "維護品項主檔",
}

CONFIGURABLE_PERMISSIONS = [
    PERMISSION_OPEN_MONITOR,
    PERMISSION_OPEN_SETTINGS,
    PERMISSION_OPEN_HISTORY,
    PERMISSION_MANAGE_MODELS,
    PERMISSION_EXPORT_RECORDS,
    PERMISSION_VIEW_ALL_RECORDS,
    PERMISSION_VIEW_SESSIONS,
    PERMISSION_USE_SIMULATION,
    PERMISSION_QC_VIEW,
    PERMISSION_QC_PRODUCT_MANAGE,
]

ROLE_PERMISSIONS = {
    ROLE_DEVELOPER: {
        PERMISSION_OPEN_SETTINGS,
        PERMISSION_OPEN_MONITOR,
        PERMISSION_OPEN_HISTORY,
        PERMISSION_MANAGE_MODELS,
        PERMISSION_EXPORT_RECORDS,
        PERMISSION_VIEW_ALL_RECORDS,
        PERMISSION_VIEW_SESSIONS,
        PERMISSION_USE_SIMULATION,
        PERMISSION_QC_VIEW,
        PERMISSION_QC_PRODUCT_MANAGE,
    },
    ROLE_MANAGER: {
        PERMISSION_OPEN_SETTINGS,
        PERMISSION_OPEN_MONITOR,
        PERMISSION_OPEN_HISTORY,
        PERMISSION_EXPORT_RECORDS,
        PERMISSION_VIEW_ALL_RECORDS,
        PERMISSION_VIEW_SESSIONS,
        PERMISSION_USE_SIMULATION,
        PERMISSION_QC_VIEW,
        PERMISSION_QC_PRODUCT_MANAGE,
    },
    ROLE_OPERATOR: {
        PERMISSION_OPEN_MONITOR,
    },
}


def role_label(role, role_labels=None):
    labels = role_labels or ROLE_LABELS
    return labels.get(role, ROLE_LABELS.get(role, role))


def has_permission(role, permission, role_permissions=None):
    if role == ROLE_DEVELOPER:
        return permission in ROLE_PERMISSIONS[ROLE_DEVELOPER]
    permissions = role_permissions or ROLE_PERMISSIONS
    return permission in permissions.get(role, set())


def default_role_passwords():
    return dict(DEFAULT_ROLE_PASSWORDS)


def default_role_permissions():
    return {role: set(permissions) for role, permissions in ROLE_PERMISSIONS.items()}


def default_role_labels():
    return dict(ROLE_LABELS)


def role_options(role_labels=None):
    if role_labels is None:
        return list(ROLE_OPTIONS)
    labels = role_labels
    ordered = []
    for role, label in labels.items():
        if role != ROLE_DEVELOPER:
            ordered.append((role, label))
    for role, label in ROLE_OPTIONS:
        if role != ROLE_DEVELOPER and role not in labels:
            ordered.append((role, label))
    if ROLE_DEVELOPER in labels:
        ordered.append((ROLE_DEVELOPER, labels[ROLE_DEVELOPER]))
    else:
        ordered.append((ROLE_DEVELOPER, ROLE_LABELS[ROLE_DEVELOPER]))
    return ordered


def protected_roles():
    return {ROLE_DEVELOPER}
