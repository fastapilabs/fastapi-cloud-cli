import contextlib
import subprocess

from pydantic import BaseModel, EmailStr, TypeAdapter, ValidationError
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient


class SignupToWaitingList(BaseModel):
    email: EmailStr
    name: str | None = None
    organization: str | None = None
    role: str | None = None
    team_size: str | None = None
    location: str | None = None
    use_case: str | None = None
    secret_code: str | None = None


def _send_waitlist_form(
    result: SignupToWaitingList,
    toolkit: RichToolkit,
) -> None:
    with toolkit.progress("Sending your request...") as progress:
        with APIClient() as client:
            with client.handle_http_errors(progress):
                response = client.post("/users/waiting-list", json=result.model_dump())

                response.raise_for_status()

        progress.log("Let's go! Thanks for your interest in FastAPI Cloud! 🚀")


def _waitlist_form(toolkit: RichToolkit) -> None:
    from rich_toolkit.form import Form

    toolkit.print(
        "We're currently in private beta. If you want to be notified when we launch, please fill out the form below.",
        tag="waitlist",
    )

    toolkit.print_line()

    email = toolkit.input(
        "Enter your email:",
        required=True,
        validator=TypeAdapter(EmailStr),
    )

    toolkit.print_line()

    result = SignupToWaitingList.model_validate({"email": email})

    if toolkit.confirm(
        "Do you want to get access faster by giving us more information?",
        tag="waitlist",
    ):
        toolkit.print_line()
        form = Form("Waitlist form", style=toolkit.style)

        form.add_input("name", label="Name", placeholder="John Doe")
        form.add_input("organization", label="Organization", placeholder="Acme Inc.")
        form.add_input("team", label="Team", placeholder="Team A")
        form.add_input("role", label="Role", placeholder="Developer")
        form.add_input("location", label="Location", placeholder="San Francisco")
        form.add_input(
            "use_case",
            label="How do you plan to use FastAPI Cloud?",
            placeholder="I'm building a web app",
        )
        form.add_input("secret_code", label="Secret code", placeholder="123456")

        result = form.run()  # type: ignore  # ty: ignore[unused-ignore-comment]

        try:
            result = SignupToWaitingList.model_validate(
                {
                    "email": email,
                    **result,  # type: ignore  # ty: ignore[unused-ignore-comment]
                },
            )
        except ValidationError:
            toolkit.print(
                "[error]Invalid form data. Please try again.[/]",
            )

            return

    toolkit.print_line()

    if toolkit.confirm(
        (
            "Do you agree to\n"
            "- Terms of Service: [link=https://fastapicloud.com/legal/terms]https://fastapicloud.com/legal/terms[/link]\n"
            "- Privacy Policy: [link=https://fastapicloud.com/legal/privacy-policy]https://fastapicloud.com/legal/privacy-policy[/link]\n"
        ),
        tag="terms",
    ):
        toolkit.print_line()

        _send_waitlist_form(
            result,
            toolkit,
        )

        with contextlib.suppress(Exception):
            subprocess.run(
                ["open", "-g", "raycast://confetti?emojis=🐔⚡"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
