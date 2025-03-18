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
  end

  def test_hourly_setpoints
    # create hash of argument values.
    args_hash = {}
    args_hash['xml_file'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-hvac-setpoints-daily-schedules.xml')
    args_hash['save_file_path'] = @tmp_hpxml_path
    args_hash['heating_setpoint_offset'] = -1.5
    args_hash['cooling_setpoint_offset'] = 2.5

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
