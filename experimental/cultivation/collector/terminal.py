"""Read optional terminal answers in a cancellable child so collection deadlines cannot leave input threads running."""

import asyncio
import sys


async def answer(question):
    print(f"{question.question}\n{question.reason}\n> ", end="", flush=True)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import sys; sys.stdout.write(sys.stdin.readline())",
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        output, _ = await process.communicate()
        return output.decode().strip() or None
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
