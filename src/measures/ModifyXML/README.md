
###### (Automatically generated documentation)

# ModifyXML

## Description

Modify the contents of an existing, valid XML file

## Modeler Description

The measure changes values of requested XML fields

## Measure Type

ModelMeasure

## Taxonomy

## Arguments

### Path to XML file

Path to existing XML file to modify
**Name:** xml_file,
**Type:** String,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Save file path

Path to save new xml file
**Name:** save_file_path,
**Type:** String,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Heating setpoint offset

How much to change heating setpoint
**Name:** heating_setpoint_offset,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Cooling setpoint offset

How much to change cooling setpoint
**Name:** cooling_setpoint_offset,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Air leakage units

What the air leakage is measured in. Valid options are: "CFM", "ACH"
**Name:** air_leakage_units,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Air leakage ofsett

How much to change the air leakage
**Name:** air_leakage_offset,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false
