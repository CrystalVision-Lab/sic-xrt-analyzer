"""OS credential vault only; never store credentials in QSettings/outbox."""

from .client import SyncError


class CredentialVault:
    def _backend(self):
        try:
            import keyring

            # Refuse plaintext/file fallback backends. OS-native backends only.
            module = keyring.get_keyring().__class__.__module__
            if not module.startswith(
                (
                    "keyring.backends.Windows",
                    "keyring.backends.macOS",
                    "keyring.backends.SecretService",
                    "keyring.backends.kwallet",
                )
            ):
                raise SyncError("OS_CREDENTIAL_VAULT_UNAVAILABLE")
            return keyring
        except ImportError:
            raise SyncError("INSTALL_SYNC_DEPENDENCIES") from None

    def get(self, endpoint, client_id):
        return self._backend().get_password("sic-xrt-sync:" + endpoint, client_id) or ""

    def set(self, endpoint, client_id, token):
        self._backend().set_password("sic-xrt-sync:" + endpoint, client_id, token)

    def delete(self, endpoint, client_id):
        backend = self._backend()
        if backend.get_password("sic-xrt-sync:" + endpoint, client_id):
            backend.delete_password("sic-xrt-sync:" + endpoint, client_id)
