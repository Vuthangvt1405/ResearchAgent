"""The app's own description of the Settings switches and the chat box pickers.

Business code builds these; a chat UI adapter turns them into its own widgets.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingSwitch:
    """One on/off row in Settings."""

    id: str  # the key the chosen value comes back under
    label: str
    initial: bool  # where the switch starts when Settings opens
    disabled: bool  # greyed out because the picked model lacks the feature
    description: str  # what the switch does, or why it is greyed out


@dataclass(frozen=True)
class PickerOption:
    """One choice in a chat box picker."""

    id: str  # the value sent back with the message
    name: str  # the label shown to the user
    selected: bool


@dataclass(frozen=True)
class Picker:
    """A chat box picker, such as Model or Effort."""

    id: str  # the key the picked value comes back under
    name: str
    options: tuple[PickerOption, ...]
