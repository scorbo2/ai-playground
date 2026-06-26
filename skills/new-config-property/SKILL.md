---
name: new-config-property
description: Adds a new configuration property to the application, with persistence and UI support.
---

## What this skill does

- Adds a new configuration property to the application
- Wires up the new property so that it is persisted automatically
- Exposes the new property to the application properties dialog so the user can view/change it

## Properties overview

The `ca.corbett.snotes.AppConfig` class is the central (singleton) manager of application configuration.
This class makes use of the `*Property` classes from the `ca.corbett.extras.properties` package in the
`swing-extras` library. A property wrapper class exists for most common types of properties:

- `BooleanProperty`: wraps a simple yes/no or on/off option, represented as a checkbox in the UI.
- `ShortTextProperty`: a single-line text input field.
- `LongTextProperty`: a multi-line text input field.
- `IntegerProperty`: for selecting a whole number from a defined range. Example: TCP port selection.
- `DecimalProperty`: for selecting a floating-point number from a defined range.
- `ColorProperty`: can be used to select a single color, or a color gradient (using a custom gradient color chooser)
- `FontProperty`: for selecting a font, with optional style selection and foreground/background color choosers.
- `ComboProperty`: for selecting an item from a predefined list of options.
- `EnumProperty`: for selecting a specific enum value from a caller-defined enum.

These property classes all extend `AbstractProperty`.

## Step-by-step instructions

- Select the most relevant property type from the list above.
- Add the new property as a new instance variable with a suitable name.
- Add a getter for the new property. Most properties do NOT have setters. They are managed via the auto-generated properties dialog.
- If it is a requirement to be able to set the new property programmatically, add a setter. The setter should invoke `save()` to immediately persist the new value.
- The `createInternalProperties()` method is the place to instantiate the new property.
- Ensure the new property has a sensible default value.
- Ensure the new property has a good internal name (see "Naming the new property")
- You can optional use `setHelpText()` (from AbstractProperty) to give the user some context about the property.
- Ensure the new property is added to the list of AbstractProperty instances returned from `createInternalProperties()`
- Compile the project to ensure it builds successfully. No need to run unit tests for this change.
- Report success to the user.

## Naming the new property

The first parameter to most property constructors is the `name` for the new property. This internal identifier
is used to categorize the property. Most importantly, this determines which tab or group the new property will
appear in, when rendered on the properties dialog. Try to match the new property to some existing group.
For example, a new property that affects the cosmetic aspects of the desktop pane should go into the
existing `UI.Desktop` group. The property name is always written as `<majorGroup>.<minorGroup>.<uniquePropertyName>`.

If the new property does not belong to any existing group, create a new major and minor group for it.

## Example

The user prompt: "I want to add a new config property to store the user's preferred name. The new property
should be in the UI.General group."

Step-by-step:
- user's name is a short string, so `ShortTextProperty` is most appropriate.
- add a new instance variable to `AppConfig` called `userPreferredName`.
- add a `getUserPreferredName()` method so the current value can be queried programmatically.
- the user did not mention setting it programmatically, so we will NOT add a setter method.
- we don't know the user's name, so the default value for the new property is empty string.
- we don't have enough context to provide meaningful help text, so we skip the call to `setHelpText()`.
- the user specifically mentioned `UI.General`, so we use `UI.General.userPreferredName` for the property name.
- we ensure the new property is added to the returned property list in `createInternalProperties()`.
- we compile the project (`mvn package` or so) and ensure the build looks good.
- we report to the user that the new property has been successfully added.

