# insert your copyright here

require 'openstudio'
require 'openstudio/measure/ShowRunnerOutput'
require 'minitest/autorun'
require 'fileutils'

require_relative '../measure'

class ModifyXMLTest < Minitest::Test
  def setup
    @oshpxml_root_path = File.absolute_path(File.join(File.dirname(__FILE__), '..', '..', '..', 'OpenStudio-HPXML'))
    @tmp_hpxml_path = File.join(File.dirname(__FILE__), 'tmp.xml')
  end

  def teardown
    File.delete(@tmp_hpxml_path) if File.exist? @tmp_hpxml_path
  end

  def test_setpoint_offsets
    # create hash of argument values.
    args_hash = {}
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base.xml')
    args_hash['save_file_path'] = @tmp_hpxml_path
    args_hash['heating_setpoint_offset'] = -1.5
    args_hash['cooling_setpoint_offset'] = 2.5

    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    # Check for expected change
    new_heating_setpoint = original_bldg.hvac_controls[0].heating_setpoint_temp + args_hash['heating_setpoint_offset'] # 66.5
    new_cooling_setpoint = original_bldg.hvac_controls[0].cooling_setpoint_temp + args_hash['cooling_setpoint_offset'] # 80.5
    assert_equal(new_heating_setpoint, hpxml_bldg.hvac_controls[0].heating_setpoint_temp)
    assert_equal(new_cooling_setpoint, hpxml_bldg.hvac_controls[0].cooling_setpoint_temp)

    # Test a file with a different way of specifying setpoints
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-hvac-setpoints-daily-schedules.xml')

    hpxml_bldg = _test_measure(args_hash)

    # Check for expected change
    new_weekday_heating_setpoints = '62.5, 62.5, 62.5, 62.5, 62.5, 62.5, 62.5, 68.5, 68.5, 64.5, 64.5, 64.5, 64.5, 64.5, 64.5, 64.5, 64.5, 66.5, 66.5, 66.5, 66.5, 66.5, 62.5, 62.5'
    new_weekend_heating_setpoints = '66.5, 66.5, 66.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5'
    new_weekday_cooling_setpoints = '78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 73.5, 73.5, 78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 76.5, 76.5, 76.5, 76.5, 76.5, 78.5, 78.5'
    new_weekend_cooling_setpoints = '76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5'
    assert_equal(new_weekday_heating_setpoints, hpxml_bldg.hvac_controls[0].weekday_heating_setpoints)
    assert_equal(new_weekend_heating_setpoints, hpxml_bldg.hvac_controls[0].weekend_heating_setpoints)
    assert_equal(new_weekday_cooling_setpoints, hpxml_bldg.hvac_controls[0].weekday_cooling_setpoints)
    assert_equal(new_weekend_cooling_setpoints, hpxml_bldg.hvac_controls[0].weekend_cooling_setpoints)
  end

  def test_change_air_leakage
    # create hash of argument values.
    args_hash = {}
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base.xml')
    args_hash['save_file_path'] = @tmp_hpxml_path
    args_hash['air_leakage_pct_change'] = -0.1

    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    new_infiltration = original_bldg.air_infiltration_measurements[0].air_leakage * ( 1 + args_hash['air_leakage_pct_change']) # 2.7
    assert_equal(new_infiltration, hpxml_bldg.air_infiltration_measurements[0].air_leakage)

    # Test a file with a different way of specifying air leakage
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-enclosure-infil-cfm50.xml')

    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    new_infiltration = original_bldg.air_infiltration_measurements[0].air_leakage * ( 1 + args_hash['air_leakage_pct_change']) # 972.0
    assert_equal(new_infiltration, hpxml_bldg.air_infiltration_measurements[0].air_leakage)

    # Test a file with a different way of specifying air leakage
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-enclosure-infil-ela.xml')

    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    new_infiltration = original_bldg.air_infiltration_measurements[0].effective_leakage_area * ( 1 + args_hash['air_leakage_pct_change']) # 110.7
    assert_equal(new_infiltration, hpxml_bldg.air_infiltration_measurements[0].effective_leakage_area)

    # Test a file with a different way of specifying air leakage
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-enclosure-infil-leakiness-description.xml')

    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    new_infiltration = original_bldg.air_infiltration_measurements[0].infiltration_volume * ( 1 + args_hash['air_leakage_pct_change']) # 19440.0
    assert_equal(new_infiltration, hpxml_bldg.air_infiltration_measurements[0].infiltration_volume)

    # Test a file with a different way of specifying air leakage
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-enclosure-infil-natural-ach.xml')

    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    new_infiltration = (original_bldg.air_infiltration_measurements[0].air_leakage * ( 1 + args_hash['air_leakage_pct_change'])).round(2) # 0.18
    assert_equal(new_infiltration, hpxml_bldg.air_infiltration_measurements[0].air_leakage)
  end

  def test_change_heating_efficiency
    # create hash of argument values.
    args_hash = {}
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base.xml')
    args_hash['save_file_path'] = @tmp_hpxml_path
    args_hash['heating_efficiency_pct_change'] = 0.1

    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    new_afue = (original_bldg.heating_systems[0].heating_efficiency_afue * ( 1 + args_hash['heating_efficiency_pct_change'])).round(2) # 1.01
    assert_equal(new_afue, hpxml_bldg.heating_systems[0].heating_efficiency_afue)

    # Test a file with a different way of specifying heating efficiency
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-hvac-air-to-air-heat-pump-1-speed.xml')

    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    new_hspf = (original_bldg.heat_pumps[0].heating_efficiency_hspf * ( 1 + args_hash['heating_efficiency_pct_change'])).round(2) # 8.47
    assert_equal(new_hspf, hpxml_bldg.heat_pumps[0].heating_efficiency_hspf)
  end

  def test_change_cooling_efficiency
    # create hash of argument values.
    args_hash = {}
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base.xml')
    args_hash['save_file_path'] = @tmp_hpxml_path
    args_hash['cooling_efficiency_pct_change'] = 0.1

    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    new_seer = (original_bldg.cooling_systems[0].cooling_efficiency_seer * ( 1 + args_hash['cooling_efficiency_pct_change'])).round(2) #
    assert_equal(new_seer, hpxml_bldg.cooling_systems[0].cooling_efficiency_seer)

    # Test a file with a different way of specifying cooling efficiency
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-hvac-multiple.xml')
    original_bldg = HPXML.new(hpxml_path: args_hash['xml_file']).buildings[0]
    hpxml_bldg = _test_measure(args_hash)

    new_efficiencies = []
    original_bldg.cooling_systems.each do |cooling_system|
      if cooling_system.cooling_efficiency_seer
        new_efficiencies << (cooling_system.cooling_efficiency_seer * ( 1 + args_hash['cooling_efficiency_pct_change'])).round(2) #
      end
      if cooling_system.cooling_efficiency_eer
        new_efficiencies << (cooling_system.cooling_efficiency_eer * ( 1 + args_hash['cooling_efficiency_pct_change'])).round(2) #
      end
      if cooling_system.cooling_efficiency_seer2
        new_efficiencies << (cooling_system.cooling_efficiency_seer2 * ( 1 + args_hash['cooling_efficiency_pct_change'])).round(2) #
      end
      if cooling_system.cooling_efficiency_ceer
        new_efficiencies << (cooling_system.cooling_efficiency_ceer * ( 1 + args_hash['cooling_efficiency_pct_change'])).round(2) #
      end
    end
    hpxml_bldg.cooling_systems.each do |new_cooling_system|
      if new_cooling_system.cooling_efficiency_seer
        assert(new_efficiencies.include? new_cooling_system.cooling_efficiency_seer)
      end
      if new_cooling_system.cooling_efficiency_eer
        assert(new_efficiencies.include? new_cooling_system.cooling_efficiency_eer)
      end
      if new_cooling_system.cooling_efficiency_seer2
        assert(new_efficiencies.include? new_cooling_system.cooling_efficiency_seer2)
      end
      if new_cooling_system.cooling_efficiency_ceer
        assert(new_efficiencies.include? new_cooling_system.cooling_efficiency_ceer)
      end
    end

    original_bldg.heat_pumps.each do |heat_pump|
      if heat_pump.cooling_efficiency_seer
        new_efficiencies << (heat_pump.cooling_efficiency_seer * ( 1 + args_hash['cooling_efficiency_pct_change'])).round(2) #
      end
      if heat_pump.cooling_efficiency_eer
        new_efficiencies << (heat_pump.cooling_efficiency_eer * ( 1 + args_hash['cooling_efficiency_pct_change'])).round(2) #
      end
      if heat_pump.cooling_efficiency_seer2
        new_efficiencies << (heat_pump.cooling_efficiency_seer2 * ( 1 + args_hash['cooling_efficiency_pct_change'])).round(2) #
      end
      if heat_pump.cooling_efficiency_ceer
        new_efficiencies << (heat_pump.cooling_efficiency_ceer * ( 1 + args_hash['cooling_efficiency_pct_change'])).round(2) #
      end
    end
    hpxml_bldg.heat_pumps.each do |new_heat_pump|
      if new_heat_pump.cooling_efficiency_seer
        assert(new_efficiencies.include? new_heat_pump.cooling_efficiency_seer)
      end
      if new_heat_pump.cooling_efficiency_eer
        assert(new_efficiencies.include? new_heat_pump.cooling_efficiency_eer)
      end
      if new_heat_pump.cooling_efficiency_seer2
        assert(new_efficiencies.include? new_heat_pump.cooling_efficiency_seer2)
      end
      if new_heat_pump.cooling_efficiency_ceer
        assert(new_efficiencies.include? new_heat_pump.cooling_efficiency_ceer)
      end
    end
  end

  def _test_measure(args_hash)
    # create an instance of the measure
    measure = ModifyXML.new

    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)
    model = OpenStudio::Model::Model.new

    # get arguments
    arguments = measure.arguments(model)
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    # populate argument with specified hash value if specified
    arguments.each do |arg|
      temp_arg_var = arg.clone
      if args_hash.key?(arg.name)
        assert(temp_arg_var.setValue(args_hash[arg.name]))
      end
      argument_map[arg.name] = temp_arg_var
    end

    # run the measure
    measure.run(model, runner, argument_map)
    result = runner.result

    # show the output
    show_output(result) unless result.value.valueName == 'Success'

    # assert that it ran correctly
    assert_equal('Success', result.value.valueName)

    # return new HPXML building
    hpxml = HPXML.new(hpxml_path: args_hash['save_file_path'])
    return hpxml.buildings[0]
  end
end
