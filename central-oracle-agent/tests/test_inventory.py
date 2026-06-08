from pathlib import Path

from oracle_db_agent.config import TargetInventory


def test_load_inventory_and_get_target(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.yml"
    inventory_path.write_text(
        """
databases:
  dev1:
    database_name: DEV
    hostname: dev-host
    dsn: dev-host:1521/DEV
    username_env: DEV_USER
    password_env: DEV_PASSWORD
    environment: dev
""",
        encoding="utf-8",
    )

    inventory = TargetInventory.load(inventory_path)
    target = inventory.get("dev1")

    assert target.name == "dev1"
    assert target.scope_label == "DEV@dev-host"
    assert target.require_start_confirmation is True
    assert target.require_mutation_approval is True


def test_infer_target_name_from_prompt(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.yml"
    inventory_path.write_text(
        """
databases:
  dev1:
    database_name: DEV
    hostname: dev-host
    dsn: dev-host:1521/DEV
    username_env: DEV_USER
    password_env: DEV_PASSWORD
  prod1:
    database_name: PROD
    hostname: prod-host
    dsn: prod-host:1521/PROD
    username_env: PROD_USER
    password_env: PROD_PASSWORD
""",
        encoding="utf-8",
    )

    inventory = TargetInventory.load(inventory_path)

    assert inventory.infer_target_name("unlock user SCOTT on prod1") == "prod1"
    assert inventory.infer_target_name("show blocking sessions target dev1") == "dev1"
