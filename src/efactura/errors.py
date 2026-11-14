"""The one error type every command and API route reports.

Codes are part of the contract with the Power Automate flow; do not rename them.
"""

LOGIN_NEEDED = "login_needed"
LOGIN_CODE_EXPIRED = "login_code_expired"
LOGIN_REFUSED = "login_refused"
INVALID_INPUT = "invalid_input"
INVALID_CUI = "invalid_cui"
NO_SPV_RIGHTS = "no_spv_rights"
ANAF_LIMIT_REACHED = "anaf_limit_reached"
ANAF_ERROR = "anaf_error"
NETWORK_ERROR = "network_error"
NOT_FOUND = "not_found"
BUSY = "busy"
CONFIG_ERROR = "config_error"
UNAUTHORIZED = "unauthorized"
INTERNAL_ERROR = "internal_error"
JEV_ERROR = "jev_error"
NOT_CLASSIFIABLE = "not_classifiable"
UPDATE_ERROR = "update_error"
BACKUP_ERROR = "backup_error"


class EfacturaError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"ok": False, "error": {"code": self.code, "message": self.message}}


def said_by(exc: Exception) -> str:
    """A network failure in words, for a message a person reads and the journal keeps.

    A request the HTTP library refused to send is named by its kind alone: its own message
    quotes the header it refused, and that header holds the key."""
    if type(exc).__name__ == "LocalProtocolError":
        return "the request could not be sent (LocalProtocolError); check the key for stray characters"
    return str(exc)
