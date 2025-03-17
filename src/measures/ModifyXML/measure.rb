# insert your copyright here

# see the URL below for information on how to write OpenStudio measures
# http://nrel.github.io/OpenStudio-user-documentation/reference/measure_writing_guide/

require 'oga'
require 'pathname'
Dir["#{File.dirname(__FILE__)}/../../OpenStudio-HPXML/HPXMLtoOpenStudio/resources/*.rb"].each do |resource_file|
  next if resource_file.include? 'minitest_helper.rb'

  require resource_file
end

# start the measure
class ModifyXML < OpenStudio::Measure::ModelMeasure
  # human readable name
  def name
    # Measure name should be the title case of the class name.
    return 'ModifyXML'
  end

  # human readable description
  def description
    return 'Modify the contents of an existing, valid XML file'
  end

  # human readable description of modeling approach
  def modeler_description
    return 'The measure changes values of requested XML fields'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = OpenStudio::Measure::OSArgumentVector.new

    # the name of the space to add to the model
    arg = OpenStudio::Measure::OSArgument.makeStringArgument('xml_file', true)
    arg.setDisplayName('Path to XML file')
    arg.setDescription('Path to existing XML file to modify')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeStringArgument('save_file_path', true)
    arg.setDisplayName('Save file path')
    arg.setDescription('Path to save new xml file')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('heating_setpoint_offset', false)
    arg.setDisplayName('Heating setpoint offset')
    arg.setDescription('How much to change heating setpoint')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('cooling_setpoint_offset', false)
    arg.setDisplayName('Cooling setpoint offset')
    arg.setDescription('How much to change cooling setpoint')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('air_leakage_pct_change', false)
    arg.setDisplayName('Air leakage percent change')
    arg.setDescription('What percentage to change the air leakage rate.
      Positive value increases air leakage, negative value decreases air leakage.
      Expressed as a decimal, 0 - 1.')
    args << arg

    return args
  end

  # define what happens when the measure is run
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)  # Do **NOT** remove this line

    # use the built-in error checking
    if !runner.validateUserArguments(arguments(model), user_arguments)
      return false
    end

    # assign the user inputs to variables
    args = runner.getArgumentValues(arguments(model), user_arguments)

    xml_file = args[:xml_file]

    unless (Pathname.new xml_file).absolute?
      xml_file = File.expand_path(xml_file)
    end

    hpxml = HPXML.new(hpxml_path: xml_file)
    hpxml_bldg = hpxml.buildings[0] # FIXME: This requires that each XML file contain only a single building

    # Modify XML fields
    if args[:heating_setpoint_offset]
      modify_heating_setpoint(hpxml_bldg, runner, args)
    end
    if args[:cooling_setpoint_offset]
      modify_cooling_setpoint(hpxml_bldg, runner, args)
    end
    if args[:air_leakage_pct_change]
      modify_air_leakage(hpxml_bldg, runner, args)
    end
    # ...

    # Save new file
    XMLHelper.write_file(hpxml.to_doc(), args[:save_file_path])
    return true
  end

  def modify_heating_setpoint(hpxml_bldg, runner, args)
    # As of 2025-02-25, this measure only modifies heating setpoint & setback (not hourly heating setpoints)
    if args[:heating_setpoint_offset].nil? || args[:weekday_heating_setpoints] || args[:weekend_heating_setpoints]
      puts 'Only heating setpoint (& setback) is supported. Not modifying heating setpoints.'
      return
    end
    # https://github.com/NREL/OpenStudio-HPXML-Calibration/blob/main/src/OpenStudio-HPXML/HPXMLtoOpenStudio/resources/hpxml.rb#L7508-L7530
    hpxml_bldg.hvac_controls[0].heating_setpoint_temp += args[:heating_setpoint_offset]
    if hpxml_bldg.hvac_controls[0].heating_setback_temp
      hpxml_bldg.hvac_controls[0].heating_setback_temp += args[:heating_setpoint_offset]
    end
  end

  def modify_cooling_setpoint(hpxml_bldg, runner, args)
    # As of 2025-02-25, this measure only modifies cooling setpoint & setback (not hourly cooling setpoints)
    if args[:cooling_setpoint_offset].nil? || args[:weekday_cooling_setpoints] || args[:weekend_cooling_setpoints]
      puts 'Only cooling setpoint (& setback) is supported. Not modifying cooling setpoints.'
      return
    end
    # https://github.com/NREL/OpenStudio-HPXML-Calibration/blob/main/src/OpenStudio-HPXML/HPXMLtoOpenStudio/resources/hpxml.rb#L7508-L7530
    hpxml_bldg.hvac_controls[0].cooling_setpoint_temp += args[:cooling_setpoint_offset]
    if hpxml_bldg.hvac_controls[0].cooling_setup_temp
      hpxml_bldg.hvac_controls[0].cooling_setup_temp += args[:cooling_setpoint_offset]
    end
  end

  def modify_air_leakage(hpxml_bldg, runner, args)
    # https://github.com/NREL/OpenStudio-HPXML-Calibration/blob/main/src/OpenStudio-HPXML/HPXMLtoOpenStudio/resources/hpxml.rb#L3277-L3288
    if hpxml_bldg.air_infiltration_measurements[0].air_leakage
      multiplier = 1 + args[:air_leakage_pct_change]
      new_infiltration = hpxml_bldg.air_infiltration_measurements[0].air_leakage * multiplier
      hpxml_bldg.air_infiltration_measurements[0].air_leakage = new_infiltration.round
    end
  end
end

# register the measure to be used by the application
ModifyXML.new.registerWithApplication
