from __future__ import annotations

import traceback
import sys
from typing import Any, Union, Protocol, runtime_checkable, Optional, TYPE_CHECKING
from typing_extensions import Self
from importlib import import_module

import revolt

if TYPE_CHECKING:
    from .help import HelpCommand

from .command import Command
from .context import Context
from .errors import CheckError, CommandNotFound, MissingSetup
from .view import StringView
from .cog import Cog

__all__ = (
    "CommandsMeta",
    "CommandsClient"
)

@runtime_checkable
class ExtensionProtocol(Protocol):
    @staticmethod
    def setup(client: CommandsClient) -> None:
        raise NotImplementedError

class CommandsMeta(type):
    _commands: list[Command]

    def __new__(cls, name: str, bases: tuple[type, ...], attrs: dict[str, Any]):
        commands: list[Command] = []
        self = super().__new__(cls, name, bases, attrs)
        for base in reversed(self.__mro__):
            for value in base.__dict__.values():
                if isinstance(value, Command):
                    commands.append(value)

        self._commands = commands

        return self


class CaseInsensitiveDict(dict):
    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key.casefold(), value)

    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key.casefold())

    def __contains__(self, key: str) -> bool:
        return super().__contains__(key.casefold())

    def get(self, key: str, default: Any = None) -> Any:
        return super().get(key.casefold(), default)

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key.casefold())


class CommandsClient(revolt.Client, metaclass=CommandsMeta):
    """Main class that adds commands, this class should be subclassed along with `revolt.Client`."""

    _commands: list[Command]

    def __init__(self, *args, help_command: Optional[HelpCommand] = None, case_insensitive: bool = False, **kwargs):
        from .help import DefaultHelpCommand, HelpCommandImpl

        self.all_commands: dict[str, Command] = {} if not case_insensitive else CaseInsensitiveDict()
        self.cogs: dict[str, Cog] = {}
        self.extensions: dict[str, ExtensionProtocol] = {}

        for command in self._commands:
            self.all_commands[command.name] = command

            for alias in command.aliases:
                self.all_commands[alias] = command

        if help_command is None:
            help_command = DefaultHelpCommand()

        self.help_command = DefaultHelpCommand()
        self.add_command(HelpCommandImpl(self))
        super().__init__(*args, **kwargs)

    @property
    def commands(self) -> list[Command]:
        return list(set(self.all_commands.values()))

    async def get_prefix(self, message: revolt.Message) -> Union[str, list[str]]:
        """Overwrite this function to set the prefix used for commands, this function is called for every message.

        Parameters
        -----------
        message: :class:`Message`
            The message that was sent

        Returns
        --------
        Union[:class:`str`, list[:class:`str`]]
            The prefix(s) for the commands
        """
        raise NotImplementedError

    def get_command(self, name: str) -> Command:
        """Gets a command.

        Parameters
        -----------
        name: :class:`str`
            The name or alias of the command

        Returns
        --------
        :class:`Command`
            The command with the name
        """
        return self.all_commands[name]

    def add_command(self, command: Command):
        """Adds a command, this is typically only used for dynamic commands, you should use the `commands.command` decorator for most usecases.

        Parameters
        -----------
        name: :class:`str`
            The name or alias of the command
        command: :class:`Command`
            The command to be added
        """
        self.all_commands[command.name] = command

        for alias in command.aliases:
            self.all_commands[alias] = command

    def remove_command(self, name: str) -> Optional[Command]:
        """Removes a command.

        Parameters
        -----------
        name: :class:`str`
            The name or alias of the command

        Returns
        --------
        Optional[:class:`Command`]
            The command that was removed
        """
        command = self.all_commands.pop(name, None)

        if command is not None:
            for alias in command.aliases:
                self.all_commands.pop(alias, None)

        return command

    def get_view(self, message: revolt.Message) -> type[StringView]:
        return StringView

    def get_context(self, message: revolt.Message) -> type[Context[Self]]:
        return Context

    async def process_commands(self, message: revolt.Message) -> Any:
        """Processes commands, if you overwrite `Client.on_message` you should manually call this function inside the event.

        Parameters
        -----------
        message: :class:`Message`
            The message to process commands on

        Returns
        --------
        Any
            The return of the command, if any
        """
        content = message.content

        if not isinstance(content, str):
            return

        prefixes = await self.get_prefix(message)

        if isinstance(prefixes, str):
            prefixes = [prefixes]

        for prefix in prefixes:
            if content.startswith(prefix):
                content = content[len(prefix):]
                break
        else:
            return

        if not content:
            return

        view = self.get_view(message)(content)

        try:
            command_name = view.get_next_word()
        except StopIteration:
            return

        context_cls = self.get_context(message)

        try:
            command = self.get_command(command_name)
        except KeyError:
            context = context_cls(None, command_name, view, message, self)
            return self.dispatch("command_error", context, CommandNotFound(command_name))

        context = context_cls(command, command_name, view, message, self)

        try:
            self.dispatch("command", context)

            if not await self.bot_check(context):
                raise CheckError(f"the global check for the command failed")

            if not await context.can_run():
                raise CheckError(f"the check(s) for the command failed")

            output = await context.invoke()
            self.dispatch("after_command_invoke", context, output)

            return output
        except Exception as e:
            await command._error_handler(command.cog or self, context, e)
            self.dispatch("command_error", context, e)

    @staticmethod
    async def on_command_error(ctx: Context, error: Exception):
        traceback.print_exception(type(error), error, error.__traceback__)

    on_message = process_commands

    async def bot_check(self, context: Context) -> bool:
        """A global check for the bot that stops commands from running on certain criteria.

        Parameters
        -----------
        context: :class:`Context`
            The context for the invokation of the command

        Returns
        --------
        :class:`bool` represents if the command should run or not
        """

        return True

    def add_cog(self, cog: Cog):
        """Adds a cog to the bot, this cog must subclass `Cog`.

        Parameters
        -----------
        cog: :class:`Cog`
            The cog to be added
        """
        cog._inject(self)

    def remove_cog(self, cog_name: str) -> Cog:
        """Removes a cog from the bot.

        Parameters
        -----------
        cog_name: :class:`str`
            The name of the cog to be removed

        Returns
        --------
        :class:`Cog`
            The cog that was removed
        """
        cog = self.cogs.pop(cog_name)
        cog._uninject(self)

        return cog

    def load_extension(self, name: str):
        """Loads an extension, this takes a module name and runs the setup function inside of it.

        Parameters
        -----------
        name: :class:`str`
            The name of the extension to be loaded
        """
        extension = import_module(name)

        if not isinstance(extension, ExtensionProtocol):
            raise MissingSetup(f"'{extension}' is missing a setup function")

        self.extensions[name] = extension
        extension.setup(self)

    def unload_extension(self, name: str):
        """Unloads an extension, this takes a module name and runs the teardown function inside of it.

        Parameters
        -----------
        name: :class:`str`
            The name of the extension to be unloaded
        """
        extension = self.extensions.pop(name)

        del sys.modules[name]

        if teardown := getattr(extension, "teardown", None):
            teardown(self)

    def reload_extension(self, name: str):
        """Reloads an extension, this will unload and reload the extension.

        Parameters
        -----------
        name: :class:`str`
            The name of the extension to be reloaded
        """
        self.unload_extension(name)
        self.load_extension(name)

    def get_cog(self, name: str) -> Cog:
        """Gets a cog from the bot.

        Parameters
        -----------
        name: :class:`str`
            The name of the cog to get

        Returns
        --------
        :class:`Cog`
            The cog that was requested
        """
        return self.cogs[name]

    def get_extension(self, name: str) -> ExtensionProtocol:
        """Gets an extension from the bot.

        Parameters
        -----------
        name: :class:`str`
            The name of the extension to get

        Returns
        --------
        :class:`ExtensionProtocol`
            The extension that was requested
        """
        return self.extensions[name]
