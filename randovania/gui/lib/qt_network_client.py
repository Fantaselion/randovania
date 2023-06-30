import datetime
import functools
import json
import webbrowser
import asyncio
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget
from qasync import asyncSlot

import randovania
from randovania.gui.lib import async_dialog, wait_dialog
from randovania.network_client.network_client import NetworkClient, ConnectionState, UnableToConnect
from randovania.network_common.error import (InvalidAction, NotAuthorizedForAction, ServerError, RequestTimeout,
                                             NotLoggedIn, UserNotAuthorized, UnsupportedClient, WrongPassword)
from randovania.network_common.multiplayer_session import (
    MultiplayerSessionEntry, MultiplayerSessionListEntry, User, MultiplayerSessionActions,
    MultiplayerWorldPickups, MultiplayerSessionAuditLog,
    WorldUserInventory)
from PySide6.QtWidgets import QDialog, QInputDialog, QLineEdit
from PySide6.QtCore import Qt


def handle_network_errors(fn):
    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        try:
            return await fn(self, *args, **kwargs)

        except InvalidAction as e:
            await async_dialog.warning(self, "Invalid action", f"{e}")

        except ServerError:
            await async_dialog.warning(self, "Server error",
                                       "An error occurred on the server while processing your request.")

        except NotLoggedIn:
            await async_dialog.warning(self, "Unauthenticated",
                                       "You must be logged in.")

        except NotAuthorizedForAction:
            await async_dialog.warning(self, "Unauthorized",
                                       "You're not authorized to perform that action.")

        except UserNotAuthorized:
            await async_dialog.warning(
                self, "Unauthorized",
                "You're not authorized to use this build.\nPlease check #dev-builds for more details.",
            )

        except UnsupportedClient as e:
            s = e.detail.replace('\n', '<br />')
            await async_dialog.warning(
                self, "Unsupported client",
                s,
            )

        except UnableToConnect as e:
            s = e.reason.replace('\n', '<br />')
            await async_dialog.warning(self, "Connection Error",
                                       f"<b>Unable to connect to the server:</b><br /><br />{s}")

        except RequestTimeout as e:
            await async_dialog.warning(self, "Connection Error",
                                       f"<b>Timeout while communicating with the server:</b><br /><br />{e}"
                                       f"<br />Further attempts will wait for longer.")

        return None

    return wrapper

class QtNetworkClient(QWidget, NetworkClient):
    Connect = Signal()
    ConnectError = Signal()
    Disconnect = Signal()
    UserChanged = Signal(User)
    ConnectionStateUpdated = Signal(ConnectionState)

    MultiplayerSessionMetaUpdated = Signal(MultiplayerSessionEntry)
    MultiplayerSessionActionsUpdated = Signal(MultiplayerSessionActions)
    MultiplayerAuditLogUpdated = Signal(MultiplayerSessionAuditLog)

    WorldPickupsUpdated = Signal(MultiplayerWorldPickups)
    WorldUserInventoryUpdated = Signal(WorldUserInventory)

    def __init__(self, user_data_dir: Path):
        super().__init__()
        NetworkClient.__init__(self, user_data_dir.joinpath("network_client"), randovania.get_configuration())
        from randovania.gui.lib import common_qt_lib
        common_qt_lib.set_default_window_icon(self)

    @NetworkClient.connection_state.setter
    def connection_state(self, value: ConnectionState):
        NetworkClient.connection_state.fset(self, value)
        self.ConnectionStateUpdated.emit(value)

    async def on_connect(self):
        await super().on_connect()
        self.Connect.emit()

    async def on_connect_error(self, error_message: str):
        await super().on_connect_error(error_message)
        self.ConnectError.emit()

    async def on_disconnect(self):
        await super().on_disconnect()
        self.Disconnect.emit()

    async def on_user_session_updated(self, new_session: dict):
        await super().on_user_session_updated(new_session)
        self.UserChanged.emit(self.current_user)

    async def on_multiplayer_session_meta_update(self, entry: MultiplayerSessionEntry):
        await super().on_multiplayer_session_meta_update(entry)
        self.MultiplayerSessionMetaUpdated.emit(entry)

    async def on_multiplayer_session_actions_update(self, actions: MultiplayerSessionActions):
        await super().on_multiplayer_session_actions_update(actions)
        self.MultiplayerSessionActionsUpdated.emit(actions)

    async def on_multiplayer_session_audit_update(self, audit_log: MultiplayerSessionAuditLog):
        await super().on_multiplayer_session_audit_update(audit_log)
        self.MultiplayerAuditLogUpdated.emit(audit_log)

    async def on_world_pickups_update(self, pickups: MultiplayerWorldPickups):
        await super().on_world_pickups_update(pickups)
        self.WorldPickupsUpdated.emit(pickups)

    async def on_world_user_inventory(self, inventory: WorldUserInventory):
        await super().on_world_user_inventory(inventory)
        self.WorldUserInventoryUpdated.emit(inventory)

    async def login_with_discord(self):
        if "discord_client_id" not in self.configuration:
            raise RuntimeError("Missing Discord configuration for Randovania")

        sid = await self.server_call("start_discord_login_flow")
        url = self.configuration["server_address"] + f"/login?sid={sid}"
        webbrowser.open(url)

    async def login_as_guest(self, name: str = "Unknown"):
        if "guest_secret" not in self.configuration:
            raise RuntimeError("Missing guest configuration for Randovania")

        from cryptography.fernet import Fernet
        fernet = Fernet(self.configuration["guest_secret"].encode("ascii"))
        login_request = fernet.encrypt(json.dumps({
            "name": name,
            "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }).encode("utf-8"))

        new_session = await self.server_call("login_with_guest", login_request)
        await self.on_user_session_updated(new_session)

    @property
    def available_login_methods(self) -> set[str]:
        methods = []
        if "guest_secret" in self.configuration:
            methods.append("guest")
        if "discord_client_id" in self.configuration:
            methods.append("discord")
        return set(methods)

    @asyncSlot()
    async def attempt_join_with_password_check(self, session: MultiplayerSessionListEntry):
        if session.has_password and not session.is_user_in_session:
            dialog = QInputDialog(self)
            dialog.setWindowTitle("Enter password")
            dialog.setLabelText("This session requires a password:")
            dialog.setWindowModality(Qt.WindowModal)
            dialog.setTextEchoMode(QLineEdit.EchoMode.Password)

            if await async_dialog.execute_dialog(dialog) != QDialog.DialogCode.Accepted:
                return

            password = dialog.textValue()
        else:
            password = None
        return await self.attempt_join(session.id, password)

    @asyncSlot()
    @handle_network_errors
    async def attempt_join(self, session_id: int, password: str | None):
        try:
            joined_session = await self.join_multiplayer_session(session_id, password)
            return joined_session

        except WrongPassword:
            await async_dialog.warning(self, "Incorrect Password", "The password entered was incorrect.")

    async def ensure_logged_in(self, parent: QWidget | None):
        if self.connection_state == ConnectionState.Connected:
            return True

        if self.connection_state.is_disconnected:
            try:
                await wait_dialog.cancellable_wait(
                    parent,
                    self.connect_to_server(),
                    "Connecting",
                    "Connecting to server...",
                )
            except (asyncio.CancelledError, UnableToConnect):
                return False

        if self.current_user is None:
            from randovania.gui.dialog.login_prompt_dialog import LoginPromptDialog
            await async_dialog.execute_dialog(LoginPromptDialog(self))

        return self.current_user is not None

