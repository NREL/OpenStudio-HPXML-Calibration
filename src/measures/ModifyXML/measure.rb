# insert your copyright here

# see the URL below for information on how to write OpenStudio measures
# http://nrel.github.io/OpenStudio-user-documentation/reference/measure_writing_guide/

require 'logger'
require 'oga'
require 'pathname'
Dir["#{File.dirname(__FILE__)}/../../OpenStudio-HPXML/HPXMLtoOpenStudio/resources/*.rb"].each do |resource_file|
  next if resource_file.include? 'minitest_helper.rb'

  require resource_file
end

# start the measure
class ModifyXML < OpenStudio::Measure::ModelMeasure
  @@logger = Logger.new($stdout)
  @@estimated_uninsulated_r_value = 4
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
    arg = OpenStudio::Measure::OSArgument.makeStringArgument('xml_file_path', true)
    arg.setDisplayName('Path to XML file')
    arg.setDescription('Path to existing XML file to modify')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeStringArgument('save_file_path', true)
    arg.setDisplayName('Save file path')
    arg.setDescription('Path to save new xml file')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('heating_setpoint_offset', false)
    arg.setDisplayName('Heating setpoint offset')
    arg.setDescription('Degrees to change heating setpoint')
    arg.setUnits('F')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('cooling_setpoint_offset', false)
    arg.setDisplayName('Cooling setpoint offset')
    arg.setDescription('Degrees to change cooling setpoint')
    arg.setUnits('F')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('air_leakage_pct_change', false)
    arg.setDisplayName('Air leakage percent change')
    arg.setDescription('Percentage to change the air leakage rate.
      Positive value increases air leakage, negative value decreases air leakage.
      Expressed as a decimal, -1 - 1.')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('heating_efficiency_pct_change', false)
    arg.setDisplayName('Heating efficiency percent change')
    arg.setDescription('Percentage to change the heating equipment efficiency.
      Positive value increases efficiency, negative value decreases efficiency.
      Expressed as a decimal, -1 - 1.')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('cooling_efficiency_pct_change', false)
    arg.setDisplayName('Cooling efficiency percent change')
    arg.setDescription('Percentage to change the cooling equipment efficiency.
      Positive value increases efficiency, negative value decreases efficiency.
      Expressed as a decimal, -1 - 1.')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('plug_load_pct_change', false)
    arg.setDisplayName('Plug load percent change')
    arg.setDescription('Percentage to change the plug load usage multiplier.
      Positive value increases load, negative value decreases load.
      Expressed as a decimal, -1 - 1.')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('roof_r_value_pct_change', false)
    arg.setDisplayName('Roof R-Value percent change')
    arg.setDescription('Percentage to change the Roof R-value.
      Positive value increases R-Value, negative value decreases R-value.
      Expressed as a decimal, -1 - 1.')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('ceiling_r_value_pct_change', false)
    arg.setDisplayName('Ceiling R-Value percent change')
    arg.setDescription('Percentage to change the ceiling (attic floor) R-value.
      Positive value increases R-Value, negative value decreases R-value.
      Expressed as a decimal, -1 - 1.')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('floor_r_value_pct_change', false)
    arg.setDisplayName('Floor R-Value percent change')
    arg.setDescription('Percentage to change the floor R-value.
      Positive value increases R-Value, negative value decreases R-value.
      Expressed as a decimal, -1 - 1.')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('above_ground_walls_r_value_pct_change', false)
    arg.setDisplayName('Above-ground wall R-Value percent change')
    arg.setDescription('Percentage to change the above-ground wall R-value.
      Positive value increases R-Value, negative value decreases R-value.
      Expressed as a decimal, -1 - 1.')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('below_ground_walls_r_value_pct_change', false)
    arg.setDisplayName('Below-ground wall R-Value percent change')
    arg.setDescription('Percentage to change the below-ground wall R-value.
      Positive value increases R-Value, negative value decreases R-value.
      Expressed as a decimal, -1 - 1.')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeDoubleArgument('slab_r_value_pct_change', false)
    arg.setDisplayName('Slab R-Value percent change')
    arg.setDescription('Percentage to change the foundation slab R-value.
      Positive value increases R-Value, negative value decreases R-value.
      Expressed as a decimal, -1 - 1.')
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

    xml_file = args[:xml_file_path]

    unless (Pathname.new xml_file).absolute?
      xml_file = File.expand_path(xml_file)
    end

    hpxml = HPXML.new(hpxml_path: xml_file)
    hpxml_bldg = hpxml.buildings[0] # FIXME: This requires that each XML file contain only a single building

    # Modify XML fields
    modify_heating_setpoint(hpxml_bldg, runner, args)
    modify_cooling_setpoint(hpxml_bldg, runner, args)
    modify_air_leakage(hpxml_bldg, runner, args)
    modify_heating_efficiency(hpxml_bldg, runner, args)
    modify_cooling_efficiency(hpxml_bldg, runner, args)
    modify_plug_loads(hpxml_bldg, runner, args)
    modify_roof_r_values(hpxml_bldg, runner, args)
    modify_ceiling_r_values(hpxml_bldg, runner, args)
    modify_floor_r_values(hpxml_bldg, runner, args)
    modify_above_ground_wall_r_values(hpxml_bldg, runner, args)
    modify_below_ground_wall_r_values(hpxml_bldg, runner, args)
    modify_slab_r_values(hpxml_bldg, runner, args)

    # Save new file
    XMLHelper.write_file(hpxml.to_doc(), args[:save_file_path])
    return true
  end

  def modify_heating_setpoint(hpxml_bldg, runner, args)
    if not args[:heating_setpoint_offset]
      runner.registerInfo('No modifier for heating setpoint provided. Not modifying heating setpoints.')
      return
    end
    hpxml_bldg.hvac_controls.each do |hvac_control|
      if hvac_control.heating_setpoint_temp
        # https://github.com/NREL/OpenStudio-HPXML-Calibration/blob/main/src/OpenStudio-HPXML/HPXMLtoOpenStudio/resources/hpxml.rb#L7581-L7603
        hvac_control.heating_setpoint_temp += args[:heating_setpoint_offset]
        if hvac_control.heating_setback_temp
          hvac_control.heating_setback_temp += args[:heating_setpoint_offset]
          # puts "New heating setback: #{hvac_control.heating_setback_temp}"
        end
        # puts "New heating setpoint: #{hvac_control.heating_setpoint_temp}"
      end
      if hvac_control.weekday_heating_setpoints
        # Assumes if weekday_heating_setpoints is present, weekend_heating_setpoints is also present
        # Turn string into array of floats
        weekday_numbers = hvac_control.weekday_heating_setpoints.split(", ").map(&:to_f)
        weekend_numbers = hvac_control.weekend_heating_setpoints.split(", ").map(&:to_f)
        # Add offset
        processed_weekday_numbers = weekday_numbers.map { |n| n + args[:heating_setpoint_offset] }
        processed_weekend_numbers = weekend_numbers.map { |n| n + args[:heating_setpoint_offset] }
        # Turn back into string
        hvac_control.weekday_heating_setpoints = processed_weekday_numbers.join(", ")
        hvac_control.weekend_heating_setpoints = processed_weekend_numbers.join(", ")
        # puts "New weekday heating setpoints: #{hvac_control.weekday_heating_setpoints}"
        # puts "New weekend heating setpoints: #{hvac_control.weekend_heating_setpoints}"
      end
    end
  end

  def modify_cooling_setpoint(hpxml_bldg, runner, args)
    if not args[:cooling_setpoint_offset]
      runner.registerInfo('No modifier for cooling setpoint provided. Not modifying cooling setpoints.')
      return
    end
    hpxml_bldg.hvac_controls.each do |hvac_control|
      if hvac_control.cooling_setpoint_temp
        hvac_control.cooling_setpoint_temp += args[:cooling_setpoint_offset]
        if hvac_control.cooling_setup_temp
          hvac_control.cooling_setup_temp += args[:cooling_setpoint_offset]
          # puts "New cooling setup: #{hvac_control.cooling_setup_temp}"
        end
        # puts "New cooling setpoint: #{hvac_control.cooling_setpoint_temp}"
      end
      if hvac_control.weekday_cooling_setpoints
        # Assumes if weekday_cooling_setpoints is present, weekend_cooling_setpoints is also present
        # Turn string into array of floats
        weekday_numbers = hvac_control.weekday_cooling_setpoints.split(", ").map(&:to_f)
        weekend_numbers = hvac_control.weekend_cooling_setpoints.split(", ").map(&:to_f)
        # Add offset
        processed_weekday_numbers = weekday_numbers.map { |n| n + args[:heating_setpoint_offset] }
        processed_weekend_numbers = weekend_numbers.map { |n| n + args[:heating_setpoint_offset] }
        # Turn back into string
        hvac_control.weekday_cooling_setpoints = processed_weekday_numbers.join(", ")
        hvac_control.weekend_cooling_setpoints = processed_weekend_numbers.join(", ")
        # puts "New weekday cooling setpoints: #{hvac_control.weekday_cooling_setpoints}"
        # puts "New weekend cooling setpoints: #{hvac_control.weekend_cooling_setpoints}"
      end
    end
  end

  def modify_air_leakage(hpxml_bldg, runner, args)
    if not args[:air_leakage_pct_change]
      runner.registerInfo('No modifier for air leakage provided. Not modifying air leakage.')
      return
    end
    multiplier = 1 + args[:air_leakage_pct_change]

    hpxml_bldg.air_infiltration_measurements.each do |air_infiltration_measurement|
      if air_infiltration_measurement.air_leakage
        new_infiltration = air_infiltration_measurement.air_leakage * multiplier
        air_infiltration_measurement.air_leakage = new_infiltration.round(2)
        # puts "New infiltration 1: #{air_infiltration_measurement.air_leakage}"
      end
      if air_infiltration_measurement.effective_leakage_area
        new_infiltration = air_infiltration_measurement.effective_leakage_area * multiplier
        air_infiltration_measurement.effective_leakage_area = new_infiltration.round(1)
        # puts "New infiltration 2: #{air_infiltration_measurement.effective_leakage_area}"
      end
      if air_infiltration_measurement.leakiness_description
        runner.registerWarning('Automatic modification of air infiltration leakiness description is not supported.')
      end
    end
  end

  def modify_heating_efficiency(hpxml_bldg, runner, args)
    if not args[:heating_efficiency_pct_change]
      runner.registerInfo('No modifier for heating efficiency provided. Not modifying heating efficiency.')
      return
    end
    multiplier = 1 + args[:heating_efficiency_pct_change]
    hpxml_bldg.heating_systems.each do |heating_system|
      if heating_system.heating_efficiency_afue
        new_afue = [heating_system.heating_efficiency_afue * multiplier, 1.0].min
        heating_system.heating_efficiency_afue = new_afue.round(2)
        # puts "New AFUE: #{heating_system.heating_efficiency_afue}"
      end
      if heating_system.heating_efficiency_percent
        new_heating_efficiency = [heating_system.heating_efficiency_percent * multiplier, 1.0].min
        heating_system.heating_efficiency_percent = new_heating_efficiency.round(2)
        # puts "New heating percent efficiency: #{heating_system.heating_efficiency_percent}"
      end
    end
    hpxml_bldg.heat_pumps.each do |heat_pump|
      if heat_pump.heating_efficiency_hspf
        new_hspf = heat_pump.heating_efficiency_hspf * multiplier
        heat_pump.heating_efficiency_hspf = new_hspf.round(2)
        # puts "New HSPF: #{heat_pump.heating_efficiency_hspf}"
      end
      if heat_pump.heating_efficiency_hspf2
        new_hspf2 = heat_pump.heating_efficiency_hspf2 * multiplier
        heat_pump.heating_efficiency_hspf2 = new_hspf2.round(2)
        # puts "New HSPF2: #{heat_pump.heating_efficiency_hspf2}"
      end
      if heat_pump.heating_efficiency_cop
        new_cop = heat_pump.heating_efficiency_cop * multiplier
        heat_pump.heating_efficiency_cop = new_cop.round(2)
        # puts "New COP: #{heat_pump.heating_efficiency_cop}"
      end
    end
  end

  def modify_cooling_efficiency(hpxml_bldg, runner, args)
    if not args[:cooling_efficiency_pct_change]
      runner.registerInfo('No modifier for cooling efficiency provided. Not modifying cooling efficiency.')
      return
    end
    multiplier = 1 + args[:cooling_efficiency_pct_change]
    hpxml_bldg.cooling_systems.each do |cooling_system|
      if cooling_system.cooling_efficiency_seer
        new_seer = cooling_system.cooling_efficiency_seer * multiplier
        cooling_system.cooling_efficiency_seer = new_seer.round(2)
        # puts "New SEER: #{cooling_system.cooling_efficiency_seer}"
      end
      if cooling_system.cooling_efficiency_seer2
        new_seer2 = cooling_system.cooling_efficiency_seer2 * multiplier
        cooling_system.cooling_efficiency_seer2 = new_seer2.round(2)
        # puts "New SEER2: #{cooling_system.cooling_efficiency_seer2}"
      end
      if cooling_system.cooling_efficiency_eer
        new_eer = cooling_system.cooling_efficiency_eer * multiplier
        cooling_system.cooling_efficiency_eer = new_eer.round(2)
        # puts "New EER: #{cooling_system.cooling_efficiency_eer}"
      end
      if cooling_system.cooling_efficiency_ceer
        new_ceer = cooling_system.cooling_efficiency_ceer * multiplier
        cooling_system.cooling_efficiency_ceer = new_ceer.round(2)
        # puts "New CEER: #{cooling_system.cooling_efficiency_ceer}"
      end
    end
    hpxml_bldg.heat_pumps.each do |heat_pump|
      if heat_pump.cooling_efficiency_seer
        new_seer = heat_pump.cooling_efficiency_seer * multiplier
        heat_pump.cooling_efficiency_seer = new_seer.round(2)
        # puts "New heat pump SEER: #{heat_pump.cooling_efficiency_seer}"
      end
      if heat_pump.cooling_efficiency_seer2
        new_seer2 = heat_pump.cooling_efficiency_seer2 * multiplier
        heat_pump.cooling_efficiency_seer2 = new_seer2.round(2)
        # puts "New heat pump SEER2: #{heat_pump.cooling_efficiency_seer2}"
      end
      if heat_pump.cooling_efficiency_eer
        new_eer = heat_pump.cooling_efficiency_eer * multiplier
        heat_pump.cooling_efficiency_eer = new_eer.round(2)
        # puts "New heat pump EER: #{heat_pump.cooling_efficiency_eer}"
      end
      if heat_pump.cooling_efficiency_ceer
        new_ceer = heat_pump.cooling_efficiency_ceer * multiplier
        heat_pump.cooling_efficiency_ceer = new_ceer.round(2)
        # puts "New heat pump CEER: #{heat_pump.cooling_efficiency_ceer}"
      end
    end
  end

  def modify_plug_loads(hpxml_bldg, runner, args)
    if not args[:plug_load_pct_change]
      runner.registerInfo('No modifier for plug loads provided. Not modifying plug loads.')
      return
    end
    multiplier = 1 + args[:plug_load_pct_change]
    hpxml_bldg.plug_loads.each do |plug_load|
      if plug_load.usage_multiplier.nil?
        plug_load.usage_multiplier = 1.0
      end
      new_multiplier = plug_load.usage_multiplier * multiplier
      plug_load.usage_multiplier = new_multiplier.round(2)
      # puts "New plug load multiplier: #{plug_load.usage_multiplier}"
    end
  end

  def modify_roof_r_values(hpxml_bldg, runner, args)
    if not args[:roof_r_value_pct_change]
      runner.registerInfo('No modifier for roof provided. Not modifying roof.')
      return
    end
    multiplier = 1 + args[:roof_r_value_pct_change]
    hpxml_bldg.roofs.each do |roof|
      if roof.insulation_assembly_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{roof.insulation_id} R-value: #{roof.insulation_assembly_r_value}"
        new_r_value = roof.insulation_assembly_r_value * multiplier
        roof.insulation_assembly_r_value = new_r_value.round(1)
        # puts "New #{roof.insulation_id} R-value: #{roof.insulation_assembly_r_value}"
      end
    end
  end

  def modify_ceiling_r_values(hpxml_bldg, runner, args)
    if not args[:ceiling_r_value_pct_change]
      runner.registerInfo('No modifier for ceiling (attic floor) provided. Not modifying ceiling.')
      return
    end
    multiplier = 1 + args[:ceiling_r_value_pct_change]
    hpxml_bldg.floors.each do |floor|
      # Check if this floor surface is a ceiling
      unless floor.is_ceiling
        next
      end
      if floor.insulation_assembly_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{floor.insulation_id} R-value: #{floor.insulation_assembly_r_value}"
        new_r_value = floor.insulation_assembly_r_value * multiplier
        floor.insulation_assembly_r_value = new_r_value.round(1)
        # puts "New #{floor.insulation_id} R-value: #{floor.insulation_assembly_r_value}"
      end
    end
  end

  def modify_floor_r_values(hpxml_bldg, runner, args)
    if not args[:floor_r_value_pct_change]
      runner.registerInfo('No modifier for floor provided. Not modifying floor.')
      return
    end
    multiplier = 1 + args[:floor_r_value_pct_change]
    hpxml_bldg.floors.each do |floor|
      # Check if this floor surface is a ceiling
      if floor.is_ceiling
        next
      end
      if floor.insulation_assembly_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{floor.insulation_id} R-value: #{floor.insulation_assembly_r_value}"
        new_r_value = floor.insulation_assembly_r_value * multiplier
        floor.insulation_assembly_r_value = new_r_value.round(1)
        # puts "New #{floor.insulation_id} R-value: #{floor.insulation_assembly_r_value}"
      end
    end
  end

  def modify_above_ground_wall_r_values(hpxml_bldg, runner, args)
    if not args[:above_ground_walls_r_value_pct_change]
      runner.registerInfo('No modifier for above-ground walls provided. Not modifying above-ground walls.')
      return
    end
    multiplier = 1 + args[:above_ground_walls_r_value_pct_change]
    (hpxml_bldg.rim_joists + hpxml_bldg.walls).each do |surface|
      if surface.insulation_assembly_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{surface.insulation_id} R-value: #{surface.insulation_assembly_r_value}"
        new_r_value = surface.insulation_assembly_r_value * multiplier
        surface.insulation_assembly_r_value = new_r_value.round(1)
        # puts "New #{surface.insulation_id} R-value: #{surface.insulation_assembly_r_value}"
      end
    end
  end

  def modify_below_ground_wall_r_values(hpxml_bldg, runner, args)
    if not args[:below_ground_walls_r_value_pct_change]
      runner.registerInfo('No modifier for below-ground walls provided. Not modifying below-ground walls.')
      return
    end
    multiplier = 1 + args[:below_ground_walls_r_value_pct_change]
    hpxml_bldg.foundation_walls.each do |foundation_wall|
      if foundation_wall.insulation_exterior_r_value && foundation_wall.insulation_exterior_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{foundation_wall.insulation_id} R-value: #{foundation_wall.insulation_exterior_r_value}"
        new_r_value = foundation_wall.insulation_exterior_r_value * multiplier
        foundation_wall.insulation_exterior_r_value = new_r_value.round(1)
        # puts "New #{foundation_wall.insulation_id} R-value: #{foundation_wall.insulation_exterior_r_value}"
      end
      if foundation_wall.insulation_interior_r_value && foundation_wall.insulation_interior_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{foundation_wall.insulation_id} R-value: #{foundation_wall.insulation_interior_r_value}"
        new_r_value = foundation_wall.insulation_interior_r_value * multiplier
        foundation_wall.insulation_interior_r_value = new_r_value.round(1)
        # puts "New #{foundation_wall.insulation_id} R-value: #{foundation_wall.insulation_interior_r_value}"
      end
      if foundation_wall.insulation_assembly_r_value && foundation_wall.insulation_assembly_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{foundation_wall.insulation_id} R-value: #{foundation_wall.insulation_assembly_r_value}"
        new_r_value = foundation_wall.insulation_assembly_r_value * multiplier
        foundation_wall.insulation_assembly_r_value = new_r_value.round(1)
        # puts "New #{foundation_wall.insulation_id} R-value: #{foundation_wall.insulation_assembly_r_value}"
      end
    end
  end

  def modify_slab_r_values(hpxml_bldg, runner, args)
    if not args[:slab_r_value_pct_change]
      runner.registerInfo('No modifier for slab provided. Not modifying slab.')
      return
    end
    multiplier = 1 + args[:slab_r_value_pct_change]
    hpxml_bldg.slabs.each do |slab|
      if slab.under_slab_insulation_r_value && slab.under_slab_insulation_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{slab.under_slab_insulation_id} R-value: #{slab.under_slab_insulation_r_value}"
        new_r_value = slab.under_slab_insulation_r_value * multiplier
        slab.under_slab_insulation_r_value = new_r_value.round(1)
        # puts "New #{slab.under_slab_insulation_id} R-value: #{slab.under_slab_insulation_r_value}"
      end
      if slab.perimeter_insulation_r_value && slab.perimeter_insulation_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{slab.perimeter_insulation_id} R-value: #{slab.perimeter_insulation_r_value}"
        new_r_value = slab.perimeter_insulation_r_value * multiplier
        slab.perimeter_insulation_r_value = new_r_value.round(1)
        # puts "New #{slab.perimeter_insulation_id} R-value: #{slab.perimeter_insulation_r_value}"
      end
      if slab.exterior_horizontal_insulation_r_value && slab.exterior_horizontal_insulation_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{slab.exterior_horizontal_insulation_id} R-value: #{slab.exterior_horizontal_insulation_r_value}"
        new_r_value = slab.exterior_horizontal_insulation_r_value * multiplier
        slab.exterior_horizontal_insulation_r_value = new_r_value.round(1)
        # puts "New #{slab.exterior_horizontal_insulation_id} R-value: #{slab.exterior_horizontal_insulation_r_value}"
      end
      if slab.gap_insulation_r_value && slab.gap_insulation_r_value > @@estimated_uninsulated_r_value
        # puts "Original #{slab.id} R-value: #{slab.gap_insulation_r_value}"
        new_r_value = slab.gap_insulation_r_value * multiplier
        slab.gap_insulation_r_value = new_r_value.round(1)
        # puts "New #{slab.id} R-value: #{slab.gap_insulation_r_value}"
      end
    end
  end
end

# register the measure to be used by the application
ModifyXML.new.registerWithApplication
