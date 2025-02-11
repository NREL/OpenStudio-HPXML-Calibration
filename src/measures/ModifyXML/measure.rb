# insert your copyright here

# see the URL below for information on how to write OpenStudio measures
# http://nrel.github.io/OpenStudio-user-documentation/reference/measure_writing_guide/

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

    arg = OpenStudio::Measure::OSArgument.makeStringArgument('xml_field', true)
    arg.setDisplayName('XML field to modify')
    arg.setDescription('XPath to the XML field to modify')
    args << arg

    arg = OpenStudio::Measure::OSArgument.makeStringArgument('change_increment', true)
    arg.setDisplayName('How much to change')
    arg.setDescription('Value to add to the XML field')
    args << arg

    return args
  end

  # define what happens when the measure is run
  def modify(model, runner, user_arguments)
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
    # xml_file_path = runner.getStringArgumentValue('xml_file', user_arguments)

    # xpath through the XML file with the user arguments
    xml_field = args[:xml_field]
    original_value = xml_file.xml_field.value

    # Update the XML field with the new value
    xml_file.xml_field.value = original_value + args[:change_increment]

    # report initial condition of model
    # runner.registerInitialCondition("The building started with #{model.getSpaces.size} spaces.")

    # add a new space to the model
    # new_space = OpenStudio::Model::Space.new(model)
    # new_space.setName(space_name)

    # echo the new space's name back to the user
    # runner.registerInfo("Space #{new_space.name} was added.")

    # report final condition of model
    # runner.registerFinalCondition("The building finished with #{model.getSpaces.size} spaces.")

    return true
  end
end

# register the measure to be used by the application
ModifyXML.new.registerWithApplication
