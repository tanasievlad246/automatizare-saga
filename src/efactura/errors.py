"""The one error type every command and API route reports.

Codes are part of the contract with the Power Automate flow; do not rename them.
"""

LOGIN_NEEDED = "login_needed"
LOGIN_CODE_EXPIRED = "login_code_expired"
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


class EfacturaError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"ok": False, "error": {"code": self.code, "message": self.message}}
