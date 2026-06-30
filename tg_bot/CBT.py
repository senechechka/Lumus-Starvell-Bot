"""Callback-токены для inline-кнопок (лимит Telegram 64 байта)."""


class CBT:
    MAIN = "0"
    BACK_MAIN = "0:back"

    NOTIFICATIONS = "1"
    NOTIF_TOGGLE = "1:t"

    COMMANDS = "2"
    CMD_LIST = "2:l"
    CMD_VIEW = "2:v"
    CMD_EDIT_BUYER = "2:eb"
    CMD_EDIT_OWNER = "2:eo"
    CMD_TOGGLE_NOTIFY = "2:tn"
    CMD_VARS = "2:vars"
    CMD_ADD = "2:add"
    CMD_DELETE = "2:del"

    GLOBAL = "3"
    GLOBAL_TOGGLE = "3:t"
    GLOBAL_EDIT = "3:e"
    GLOBAL_VARS = "3:vars"

    CONFIGS = "4"
    CONFIG_UPLOAD = "4:up"
    CONFIG_DOWNLOAD = "4:dl"

    PLUGINS = "5"
    PLUGIN_ADD = "5:add"
    PLUGIN_VIEW = "5:v"
    PLUGIN_TOGGLE = "5:t"
    PLUGIN_DELETE = "5:del"
    PLUGIN_MENU = "5:m"
    PLUGIN_CMDS = "5:c"

    COPY_VAR = "6:cv"

    CANCEL = "99"
