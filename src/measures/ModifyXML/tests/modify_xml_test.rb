# insert your copyright here

require 'openstudio'
require 'openstudio/measure/ShowRunnerOutput'
require 'minitest/autorun'
require 'fileutils'

require_relative '../measure'

class ModifyXMLTest < Minitest::Test
  @@estimated_uninsulated_r_value = 4

  def setup
    @oshpxml_root_path = File.absolute_path(File.join(File.dirname(__FILE__), '..', '..', '..', 'OpenStudio-HPXML'))
    @tmp_hpxml_path = File.join(File.dirname(__FILE__), 'tmp.xml')
  end

  def teardown
    File.delete(@tmp_hpxml_path) if File.exist? @tmp_hpxml_path
  end

  def test_setpoint_offsets
    files_to_test = [
      'base.xml',
      'base-hvac-setpoints-daily-schedules.xml',
      'base-hvac-setpoints-daily-setbacks.xml',
    ]

    # Run test on each sample file
    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['heating_setpoint_offset'] = -1.5
      args_hash['cooling_setpoint_offset'] = 2.5

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      # Check for expected change
      original_bldg.hvac_controls.each do |hvac_control|
        new_setpoint = hpxml_bldg.hvac_controls.find{ |control| control.id == hvac_control.id }
        if hvac_control.heating_setpoint_temp
          expected_setpoint = (hvac_control.heating_setpoint_temp + args_hash['heating_setpoint_offset']).round(2)
          assert_equal(expected_setpoint, new_setpoint.heating_setpoint_temp)
        end
        if hvac_control.heating_setback_temp
          expected_setback = (hvac_control.heating_setback_temp + args_hash['heating_setpoint_offset']).round(2)
          assert_equal(expected_setback, new_setpoint.heating_setback_temp)
        end
        if hvac_control.cooling_setpoint_temp
          expected_setpoint = (hvac_control.cooling_setpoint_temp + args_hash['cooling_setpoint_offset']).round(2)
          assert_equal(expected_setpoint, new_setpoint.cooling_setpoint_temp)
        end
        if hvac_control.cooling_setup_temp
          expected_setup = (hvac_control.cooling_setup_temp + args_hash['cooling_setpoint_offset']).round(2)
          assert_equal(expected_setup, new_setpoint.cooling_setup_temp)
        end
        if hvac_control.weekday_heating_setpoints
          new_weekday_heating_setpoints = '62.5, 62.5, 62.5, 62.5, 62.5, 62.5, 62.5, 68.5, 68.5, 64.5, 64.5, 64.5, 64.5, 64.5, 64.5, 64.5, 64.5, 66.5, 66.5, 66.5, 66.5, 66.5, 62.5, 62.5'
          new_weekend_heating_setpoints = '66.5, 66.5, 66.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5, 68.5'
          new_weekday_cooling_setpoints = '78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 73.5, 73.5, 78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 78.5, 76.5, 76.5, 76.5, 76.5, 76.5, 78.5, 78.5'
          new_weekend_cooling_setpoints = '76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5, 76.5'
          assert_equal(new_weekday_heating_setpoints, new_setpoint.weekday_heating_setpoints)
          assert_equal(new_weekend_heating_setpoints, new_setpoint.weekend_heating_setpoints)
          assert_equal(new_weekday_cooling_setpoints, new_setpoint.weekday_cooling_setpoints)
          assert_equal(new_weekend_cooling_setpoints, new_setpoint.weekend_cooling_setpoints)
        end
      end
    end
  end

  def test_change_air_leakage
    files_to_test = [
      'base.xml',
      'base-enclosure-infil-cfm50.xml',
      'base-enclosure-infil-ela.xml',
      # We do not support qualitative infiltration descriptions
      # 'base-enclosure-infil-leakiness-description.xml',
      'base-enclosure-infil-natural-ach.xml',
    ]

    # Run test on each sample file
    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['air_leakage_multiplier'] = 0.9

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      original_bldg.air_infiltration_measurements.each do |infiltration_measurement|
        new_infiltration = hpxml_bldg.air_infiltration_measurements.find{ |infil| infil.id == infiltration_measurement.id }
        if infiltration_measurement.air_leakage
          expected_infiltration = (infiltration_measurement.air_leakage * args_hash['air_leakage_multiplier']).round(2)
          assert_equal(expected_infiltration, new_infiltration.air_leakage)
        end
        if infiltration_measurement.effective_leakage_area
          expected_infiltration = (infiltration_measurement.effective_leakage_area * args_hash['air_leakage_multiplier']).round(2)
          assert_equal(expected_infiltration, new_infiltration.effective_leakage_area)
        end
      end
    end
  end

  def test_change_heating_efficiency
    # create hash of argument values.
    args_hash = {}
    args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-hvac-multiple.xml')
    args_hash['save_file_path'] = @tmp_hpxml_path
    args_hash['heating_efficiency_multiplier'] = 1.05

    original_bldg = _get_hpxml_building(args_hash)
    hpxml_bldg = _test_measure(args_hash)

    # Test heating systems
    original_bldg.heating_systems.each do |heating_system|
      new_heating_system = hpxml_bldg.heating_systems.find{ |h| h.id == heating_system.id }
      if heating_system.heating_efficiency_afue
        expected_efficiency = (heating_system.heating_efficiency_afue * args_hash['heating_efficiency_multiplier']).round(2)
        if expected_efficiency > 1.0
          expected_efficiency = heating_system.heating_efficiency_afue
        end
        assert_equal(expected_efficiency, new_heating_system.heating_efficiency_afue)
      end
      if heating_system.heating_efficiency_percent
        expected_efficiency = (heating_system.heating_efficiency_percent * args_hash['heating_efficiency_multiplier']).round(2)
        if expected_efficiency > 1.0
          expected_efficiency = heating_system.heating_efficiency_percent
        end
        assert_equal(expected_efficiency, new_heating_system.heating_efficiency_percent)
      end
    end

    # Test heat pumps
    original_bldg.heat_pumps.each do |heat_pump|
      new_heat_pump = hpxml_bldg.heat_pumps.find{ |hp| hp.id == heat_pump.id }
      if heat_pump.heating_efficiency_hspf
        expected_efficiency = (heat_pump.heating_efficiency_hspf * args_hash['heating_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_heat_pump.heating_efficiency_hspf)
      end
      if heat_pump.heating_efficiency_hspf2
        expected_efficiency = (heat_pump.heating_efficiency_hspf2 * args_hash['heating_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_heat_pump.heating_efficiency_hspf2)
      end
      if heat_pump.heating_efficiency_cop
        expected_efficiency = (heat_pump.heating_efficiency_cop * args_hash['heating_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_heat_pump.heating_efficiency_cop)
      end
    end
  end

  def test_change_cooling_efficiency
    # create hash of argument values.
    args_hash = {}
    args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', 'base-hvac-multiple.xml')
    args_hash['save_file_path'] = @tmp_hpxml_path
    args_hash['cooling_efficiency_multiplier'] = 0.95

    original_bldg = _get_hpxml_building(args_hash)
    hpxml_bldg = _test_measure(args_hash)

    # Test cooling systems
    original_bldg.cooling_systems.each do |cooling_system|
      new_cooling_system = hpxml_bldg.cooling_systems.find{ |c| c.id == cooling_system.id }
      if cooling_system.cooling_efficiency_seer
        expected_efficiency = (cooling_system.cooling_efficiency_seer * args_hash['cooling_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_cooling_system.cooling_efficiency_seer)
      end
      if cooling_system.cooling_efficiency_eer
        expected_efficiency = (cooling_system.cooling_efficiency_eer * args_hash['cooling_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_cooling_system.cooling_efficiency_eer)
      end
      if cooling_system.cooling_efficiency_seer2
        expected_efficiency = (cooling_system.cooling_efficiency_seer2 * args_hash['cooling_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_cooling_system.cooling_efficiency_seer2)
      end
      if cooling_system.cooling_efficiency_ceer
        expected_efficiency = (cooling_system.cooling_efficiency_ceer * args_hash['cooling_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_cooling_system.cooling_efficiency_ceer)
      end
    end

    # Test heat pumps
    original_bldg.heat_pumps.each do |heat_pump|
      new_heat_pump = hpxml_bldg.heat_pumps.find{ |hp| hp.id == heat_pump.id }
      if heat_pump.cooling_efficiency_seer
        expected_efficiency = (heat_pump.cooling_efficiency_seer * args_hash['cooling_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_heat_pump.cooling_efficiency_seer)
      end
      if heat_pump.cooling_efficiency_eer
        expected_efficiency = (heat_pump.cooling_efficiency_eer * args_hash['cooling_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_heat_pump.cooling_efficiency_eer)
      end
      if heat_pump.cooling_efficiency_seer2
        expected_efficiency = (heat_pump.cooling_efficiency_seer2 * args_hash['cooling_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_heat_pump.cooling_efficiency_seer2)
      end
      if heat_pump.cooling_efficiency_ceer
        expected_efficiency = (heat_pump.cooling_efficiency_ceer * args_hash['cooling_efficiency_multiplier']).round(2)
        assert_equal(expected_efficiency, new_heat_pump.cooling_efficiency_ceer)
      end
    end
  end

  def test_misc_load_change
    files_to_test = [
      'base.xml',
      'base-misc-usage-multiplier.xml',
      'base-misc-loads-large-uncommon.xml'
    ]

    # Run test on each sample file
    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['misc_load_multiplier'] = 1.05

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      original_bldg.plug_loads.each do |plug_load|
        new_plug_load = hpxml_bldg.plug_loads.find{ |pl| pl.id == plug_load.id }
        plug_load.usage_multiplier ||= 1.0
        expected_usage_multiplier = (plug_load.usage_multiplier * args_hash['misc_load_multiplier']).round(2)
        assert_equal(expected_usage_multiplier, new_plug_load.usage_multiplier)
      end
      original_bldg.fuel_loads.each do |fuel_load|
        new_fuel_load = hpxml_bldg.fuel_loads.find{ |fl| fl.id == fuel_load.id }
        fuel_load.usage_multiplier ||= 1.0
        expected_usage_multiplier = (fuel_load.usage_multiplier * args_hash['misc_load_multiplier']).round(2)
        assert_equal(expected_usage_multiplier, new_fuel_load.usage_multiplier)
      end
      original_bldg.pools.each do |pool|
        new_pool = hpxml_bldg.pools.find{ |pol| pol.id == pool.id }
        pool.pump_usage_multiplier ||= 1.0
        pool.heater_usage_multiplier ||= 1.0
        expected_pump_usage_multiplier = (pool.pump_usage_multiplier * args_hash['misc_load_multiplier']).round(2)
        assert_equal(expected_pump_usage_multiplier, new_pool.pump_usage_multiplier)
        expected_heater_usage_multiplier = (pool.heater_usage_multiplier * args_hash['misc_load_multiplier']).round(2)
        assert_equal(expected_heater_usage_multiplier, new_pool.heater_usage_multiplier)
      end
      original_bldg.permanent_spas.each do |permanent_spa|
        new_pool = hpxml_bldg.permanent_spas.find{ |spa| spa.id == permanent_spa.id }
        permanent_spa.pump_usage_multiplier ||= 1.0
        permanent_spa.heater_usage_multiplier ||= 1.0
        expected_pump_usage_multiplier = (permanent_spa.pump_usage_multiplier * args_hash['misc_load_multiplier']).round(2)
        assert_equal(expected_pump_usage_multiplier, new_pool.pump_usage_multiplier)
        expected_heater_usage_multiplier = (permanent_spa.heater_usage_multiplier * args_hash['misc_load_multiplier']).round(2)
        assert_equal(expected_heater_usage_multiplier, new_pool.heater_usage_multiplier)
      end
    end
  end

  def test_above_ground_r_value_change
    files_to_test = [
      'base.xml',
      'base-atticroof-cathedral.xml',
      'base-atticroof-flat.xml',
      'base-enclosure-floortypes.xml',
    ]

    # Run test on each sample file
    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['roof_r_value_multiplier'] = 1.05
      args_hash['ceiling_r_value_multiplier'] = 1.05
      args_hash['above_ground_walls_r_value_multiplier'] = 1.05
      args_hash['floor_r_value_multiplier'] = 1.05

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      # Test roof surfaces
      original_bldg.roofs.each do |roof|
        new_building_roof = hpxml_bldg.roofs.find{ |rf| rf.id == roof.id }
        if roof.insulation_assembly_r_value && roof.insulation_assembly_r_value > @@estimated_uninsulated_r_value
          expected_r_value = (roof.insulation_assembly_r_value * args_hash['roof_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_building_roof.insulation_assembly_r_value)
        end
      end

      # Test ceiling (attic floor) surfaces
      original_bldg.floors.each do |floor|
        unless floor.is_ceiling
          next
        end
        new_ceiling_surface = hpxml_bldg.floors.find{ |ceiling| ceiling.id == floor.id }
        if floor.insulation_assembly_r_value && floor.insulation_assembly_r_value > @@estimated_uninsulated_r_value
          expected_r_value = (floor.insulation_assembly_r_value * args_hash['ceiling_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_ceiling_surface.insulation_assembly_r_value)
        end
      end

      # Test walls and rim joists
      (original_bldg.rim_joists + original_bldg.walls).each do |surface|
        new_building_surface = (hpxml_bldg.rim_joists + hpxml_bldg.walls).find{ |ag_wall| ag_wall.id == surface.id }
        if surface.insulation_assembly_r_value && surface.insulation_assembly_r_value > @@estimated_uninsulated_r_value
          expected_r_value = (surface.insulation_assembly_r_value * args_hash['above_ground_walls_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_building_surface.insulation_assembly_r_value)
        end
      end

      # Test floors
      original_bldg.floors.each do |floor|
        new_floor = hpxml_bldg.floors.find{ |fl| fl.id == floor.id }
        if floor.insulation_assembly_r_value && floor.insulation_assembly_r_value > @@estimated_uninsulated_r_value
          expected_r_value = (floor.insulation_assembly_r_value * args_hash['floor_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_floor.insulation_assembly_r_value)
        end
      end
    end
  end

  def test_below_ground_r_value_change
    files_to_test = [
      'base.xml',
      'base-foundation-conditioned-basement-slab-insulation.xml',
      'base-foundation-slab.xml',
      'base-foundation-unconditioned-basement.xml',
      'base-foundation-unconditioned-basement-wall-insulation.xml',
    ]

    # Run test on each sample file
    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['below_ground_walls_r_value_multiplier'] = 1.05

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      original_bldg.foundation_walls.each do |foundation_wall|
        new_foundation_wall = hpxml_bldg.foundation_walls.find{ |bg_wall| bg_wall.id == foundation_wall.id }
        if foundation_wall.insulation_exterior_r_value != 0 && foundation_wall.is_thermal_boundary
          expected_r_value = (foundation_wall.insulation_exterior_r_value * args_hash['below_ground_walls_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_foundation_wall.insulation_exterior_r_value)
        end
        if foundation_wall.insulation_interior_r_value != 0 && foundation_wall.is_thermal_boundary
          expected_r_value = (foundation_wall.insulation_interior_r_value * args_hash['below_ground_walls_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_foundation_wall.insulation_interior_r_value)
        end
      end
    end
  end

  def test_slab_r_value_change
    files_to_test = [
      'base.xml',
      'base-foundation-conditioned-basement-slab-insulation.xml',
      'base-foundation-slab.xml',
      'base-foundation-unconditioned-basement.xml',
      'base-foundation-unconditioned-basement-wall-insulation.xml',
    ]

    # Run test on each sample file
    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['slab_r_value_multiplier'] = 1.05

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      original_bldg.slabs.each do |slab|
        new_slab = hpxml_bldg.slabs.find{ |slb| slb.id == slab.id }
        if slab.under_slab_insulation_r_value && slab.is_thermal_boundary
          expected_r_value = (slab.under_slab_insulation_r_value * args_hash['slab_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_slab.under_slab_insulation_r_value)
        end
        if slab.perimeter_insulation_r_value && slab.is_thermal_boundary
          expected_r_value = (slab.perimeter_insulation_r_value * args_hash['slab_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_slab.perimeter_insulation_r_value)
        end
        if slab.exterior_horizontal_insulation_r_value && slab.is_thermal_boundary
          expected_r_value = (slab.exterior_horizontal_insulation_r_value * args_hash['slab_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_slab.exterior_horizontal_insulation_r_value)
        end
        if slab.gap_insulation_r_value && slab.is_thermal_boundary
          expected_r_value = (slab.gap_insulation_r_value * args_hash['slab_r_value_multiplier']).round(1)
          assert_equal(expected_r_value, new_slab.gap_insulation_r_value)
        end
      end
    end
  end

  def test_water_heater_efficiency_and_usage
    files_to_test = [
      'base-dhw-tank-gas-ef.xml',
      'base-appliances-modified.xml',
      'base-dhw-tank-heat-pump-ef.xml',
    ]

    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['water_heater_efficiency_multiplier'] = 0.95
      args_hash['water_fixtures_usage_multiplier'] = 0.95

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      original_bldg.water_heating.water_fixtures_usage_multiplier ||= 1.0
      expected_usage_multiplier = (original_bldg.water_heating.water_fixtures_usage_multiplier * args_hash['water_fixtures_usage_multiplier']).round(2)
      assert_equal(expected_usage_multiplier, hpxml_bldg.water_heating.water_fixtures_usage_multiplier)

      # Test water heating systems
      original_bldg.water_heating_systems.each do |water_heating_system|
        new_water_heating_system = hpxml_bldg.water_heating_systems.find{ |dhw| dhw.id == water_heating_system.id }
        if water_heating_system.energy_factor
          if water_heating_system.water_heater_type == HPXML::WaterHeaterTypeHeatPump
            expected_efficiency = [[(water_heating_system.energy_factor * args_hash['water_heater_efficiency_multiplier']).round(2), 1.01].max, 5.0].min
          else
            expected_efficiency = [(water_heating_system.energy_factor * args_hash['water_heater_efficiency_multiplier']).round(2), 0.99].min
          end
          assert_equal(expected_efficiency, new_water_heating_system.energy_factor)
        end
        if water_heating_system.uniform_energy_factor
          if water_heating_system.water_heater_type == HPXML::WaterHeaterTypeHeatPump
            expected_efficiency = [[(water_heating_system.uniform_energy_factor * args_hash['water_heater_efficiency_multiplier']).round(2), 1.01].max, 5.0].min
          else
            expected_efficiency = [(water_heating_system.uniform_energy_factor * args_hash['water_heater_efficiency_multiplier']).round(2), 0.99].min
          end
          assert_equal(expected_efficiency, new_water_heating_system.uniform_energy_factor)
        end
      end
    end
  end

  def test_lighting_load_change
    files_to_test = [
      'base.xml',
      'base-misc-usage-multiplier.xml',
    ]

    # Run test on each sample file
    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['lighting_load_multiplier'] = 1.05

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      new_lighting_multiplier = hpxml_bldg.lighting.interior_usage_multiplier
      original_bldg.lighting.interior_usage_multiplier ||= 1.0
      expected_usage_multiplier = (original_bldg.lighting.interior_usage_multiplier * args_hash['lighting_load_multiplier']).round(2)
      assert_equal(expected_usage_multiplier, new_lighting_multiplier)
    end
  end

  def test_window_ufactor_and_shgc
    files_to_test = [
      'base.xml',
      'base-enclosure-windows-physical-properties.xml'
    ]

    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['window_u_factor_multiplier'] = 0.95
      args_hash['window_shgc_multiplier'] = 0.95

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      # Test water heating systems
      original_bldg.windows.each do |window|
        new_window = hpxml_bldg.windows.find{ |wd| wd.id == window.id }
        if window.ufactor
          expected_efficiency = (window.ufactor * args_hash['window_u_factor_multiplier']).round(2)
          assert_equal(expected_efficiency, new_window.ufactor)
        end
        if window.shgc
          expected_efficiency = [(window.shgc * args_hash['window_shgc_multiplier']).round(2), 0.99].min
          assert_equal(expected_efficiency, new_window.shgc)
        end
      end
    end
  end

  def test_appliance_usage
    files_to_test = [
      'base.xml',
      'base-appliances-modified.xml',
    ]

    files_to_test.each do |file|
      # create hash of argument values.
      args_hash = {}
      args_hash['xml_file_path'] = File.join(@oshpxml_root_path, 'workflow', 'sample_files', file)
      args_hash['save_file_path'] = @tmp_hpxml_path
      args_hash['appliance_usage_multiplier'] = 1.05

      original_bldg = _get_hpxml_building(args_hash)
      hpxml_bldg = _test_measure(args_hash)

      # Test appliances
      # Fridge
      original_bldg.refrigerators.each do |refrigerator|
        new_refrigerator = hpxml_bldg.refrigerators.find{ |fridge| fridge.id == refrigerator.id }
        if refrigerator.usage_multiplier
          expected_efficiency = (refrigerator.usage_multiplier * args_hash['appliance_usage_multiplier']).round(2)
          assert_equal(expected_efficiency, new_refrigerator.usage_multiplier)
        end
      end
      # Clothes washer
      original_bldg.clothes_washers.each do |clothes_washer|
        new_washer = hpxml_bldg.clothes_washers.find{ |cw| cw.id == clothes_washer.id }
        if clothes_washer.usage_multiplier
          expected_efficiency = (clothes_washer.usage_multiplier * args_hash['appliance_usage_multiplier']).round(2)
          assert_equal(expected_efficiency, new_washer.usage_multiplier)
        end
      end
      # Clothes dryer
      original_bldg.clothes_dryers.each do |clothes_dryer|
        new_dryer = hpxml_bldg.clothes_dryers.find{ |cd| cd.id == clothes_dryer.id }
        if clothes_dryer.usage_multiplier
          expected_efficiency = (clothes_dryer.usage_multiplier * args_hash['appliance_usage_multiplier']).round(2)
          assert_equal(expected_efficiency, new_dryer.usage_multiplier)
        end
      end
      # Dishwasher
      original_bldg.dishwashers.each do |dishwasher|
        new_dishwasher = hpxml_bldg.dishwashers.find{ |dw| dw.id == dishwasher.id }
        if dishwasher.usage_multiplier
          expected_efficiency = (dishwasher.usage_multiplier * args_hash['appliance_usage_multiplier']).round(2)
          assert_equal(expected_efficiency, new_dishwasher.usage_multiplier)
        end
      end
      # Freezer
      original_bldg.freezers.each do |freezer|
        new_freezer = hpxml_bldg.freezers.find{ |free| free.id == freezer.id }
        if freezer.usage_multiplier
          expected_efficiency = (freezer.usage_multiplier * args_hash['appliance_usage_multiplier']).round(2)
          assert_equal(expected_efficiency, new_freezer.usage_multiplier)
        end
      end
      # Range
      original_bldg.cooking_ranges.each do |cooking_range|
        new_range = hpxml_bldg.cooking_ranges.find{ |range| range.id == cooking_range.id }
        if cooking_range.usage_multiplier
          expected_efficiency = (cooking_range.usage_multiplier * args_hash['appliance_usage_multiplier']).round(2)
          assert_equal(expected_efficiency, new_range.usage_multiplier)
        end
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

  def _get_hpxml_building(args_hash)
    hpxml = HPXML.new(hpxml_path: args_hash['xml_file_path'])
    hpxml_bldg = hpxml.buildings[0]

    # Apply OS-HPXML defaults to any un-populated fields
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)
    epw_path = Location.get_epw_path(hpxml_bldg, args_hash['xml_file_path'])
    weather = WeatherFile.new(epw_path: epw_path, runner: runner)
    Defaults.apply(runner, hpxml, hpxml_bldg, weather)

    return hpxml_bldg
  end
end
