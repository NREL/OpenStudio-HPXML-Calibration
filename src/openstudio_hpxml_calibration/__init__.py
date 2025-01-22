import subprocess
import click


@click.group()
def cli() -> None:
    pass


@cli.command()
def openstudio_version() -> None:
    resp = subprocess.run(
        ["openstudio", "openstudio_version"], capture_output=True, check=True
    )
    print(resp.stdout.decode())
