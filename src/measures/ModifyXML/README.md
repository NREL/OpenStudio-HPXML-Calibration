
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

### Air leakage percent change

What percentage to change the air leakage rate.
      Positive value increases air leakage, negative value decreases air leakage.
      Expressed as a decimal, 0 - 1.
**Name:** air_leakage_pct_change,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false
