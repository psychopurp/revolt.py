import asyncio
import aiohttp
import revolt
import logging


from revolt.types.gateway import InteractionEventPayload
from revolt.types.message import Component

logger = logging.getLogger("revolt")
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)


class Client(revolt.Client):
    async def on_interaction(
        self, interaction: InteractionEventPayload, message: revolt.Message
    ) -> None:
        logger.info("interaction %s", interaction)
        user = self.get_user(interaction["author_id"])
        await message.channel.send(
            f"Username: {user.name} Your choice is: {interaction['content']} "
        )
        components = message.components
        components[0]["label"] = "edited"
        components[0]["enabled"] = False

        # update the button component's label
        await message.edit(content="edited", components=components)

    async def on_message(self, message: revolt.Message):
        if message.content == "/button":
            await message.channel.send(
                "you have these options",
                components=[
                    Component(
                        type="button",
                        style="color:white; backgroundColor:green; fontSize:16px; fontWeight:400;",
                        label="continue",
                        enabled=True,
                    ),
                    Component(
                        type="button", style="color:green", label="quit", enabled=True
                    ),
                    Component(
                        type="button", style="color:red", label="restart", enabled=False
                    ),
                ],
            )


async def main():
    async with aiohttp.ClientSession() as session:
        client = Client(
            session,
            "Your Bot Token Here",
            api_url="Your API Endpoint",
        )
        await client.start()


asyncio.run(main())
