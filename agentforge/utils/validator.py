"""
Ejecuta comandos de validacion sobre el output generado.

Se usa subprocess async (asyncio.create_subprocess_shell) para no bloquear
el event loop mientras terraform validate o tfsec corren en background.

Por que validar automaticamente:
  - qwen2.5-coder:7b genera HCL invalido ocasionalmente
  - Detectarlo aqui evita que Claude tenga que leer output roto
  - El error exacto del validador se incluye en audit.json para re-prompting
"""

import asyncio

from agentforge.models import ValidationDefinition, ValidationResult


async def run_validation(
    validation: ValidationDefinition,
    task_id: str,
) -> ValidationResult:
    """
    Corre el comando de validacion definido en el manifest.

    Args:
        validation: Configuracion del comando (command, working_dir, expected_exit_code).
        task_id: Solo para logging — no afecta la ejecucion.

    Returns:
        ValidationResult con exit_code, stdout, stderr y passed=True/False.
    """
    if not validation.command:
        # Manifest sin validacion declarada — se considera exitosa
        return ValidationResult(
            command="",
            exit_code=0,
            stdout="No validation configured",
            stderr="",
            passed=True,
        )

    # Reemplazar placeholder {task_id} en el working_dir si esta presente
    working_dir = validation.working_dir.replace("{task_id}", task_id) or None

    try:
        proc = await asyncio.create_subprocess_shell(
            validation.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=60,  # validaciones no deben tardar mas de 1 minuto
        )

        exit_code = proc.returncode or 0
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        return ValidationResult(
            command=validation.command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            passed=(exit_code == validation.expected_exit_code),
        )

    except asyncio.TimeoutError:
        return ValidationResult(
            command=validation.command,
            exit_code=-1,
            stdout="",
            stderr="Validation timed out after 60 seconds",
            passed=False,
        )
    except FileNotFoundError as e:
        # El comando no existe en PATH (ej: terraform no instalado)
        return ValidationResult(
            command=validation.command,
            exit_code=-1,
            stdout="",
            stderr=f"Command not found: {e}",
            passed=False,
        )
