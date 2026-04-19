"""
Ejecuta comandos de validacion sobre el output generado.

Se usa subprocess async (asyncio.create_subprocess_shell) para no bloquear
el event loop mientras terraform validate o tfsec corren en background.

Por que validar automaticamente:
  - qwen2.5-coder:7b genera HCL invalido ocasionalmente
  - Detectarlo aqui evita que Claude tenga que leer output roto
  - El error exacto del validador se incluye en audit.json para re-prompting
"""

import ast
import asyncio
import json as json_module

from agentforge.models import ValidationDefinition, ValidationResult


def run_builtin_validation(content: str, output_format: str) -> ValidationResult | None:
    """
    Valida el contenido usando validadores built-in segun el formato de output.

    Corre sincrónicamente antes de cualquier comando externo.
    Retorna None si no hay validador built-in para el formato dado.
    """
    if output_format == "python":
        try:
            ast.parse(content)
            return ValidationResult(
                command="ast.parse",
                exit_code=0,
                stdout="Syntax OK",
                stderr="",
                passed=True,
            )
        except SyntaxError as e:
            return ValidationResult(
                command="ast.parse",
                exit_code=1,
                stdout="",
                stderr=f"SyntaxError: {e}",
                passed=False,
            )
    elif output_format == "json":
        try:
            json_module.loads(content)
            return ValidationResult(
                command="json.loads",
                exit_code=0,
                stdout="Valid JSON",
                stderr="",
                passed=True,
            )
        except json_module.JSONDecodeError as e:
            return ValidationResult(
                command="json.loads",
                exit_code=1,
                stdout="",
                stderr=f"JSONDecodeError: {e}",
                passed=False,
            )
    return None


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
