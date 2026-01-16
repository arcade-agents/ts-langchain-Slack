from arcadepy import AsyncArcade
from dotenv import load_dotenv
from google.adk import Agent, Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService, Session
from google_adk_arcade.tools import get_arcade_tools
from google.genai import types
from human_in_the_loop import auth_tool, confirm_tool_usage

import os

load_dotenv(override=True)


async def main():
    app_name = "my_agent"
    user_id = os.getenv("ARCADE_USER_ID")

    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()
    client = AsyncArcade()

    agent_tools = await get_arcade_tools(
        client, toolkits=["Slack"]
    )

    for tool in agent_tools:
        await auth_tool(client, tool_name=tool.name, user_id=user_id)

    agent = Agent(
        model=LiteLlm(model=f"openai/{os.environ["OPENAI_MODEL"]}"),
        name="google_agent",
        instruction="# Introduction
Welcome to the Slack AI Agent! This agent is designed to facilitate communication and streamline interactions within Slack. By utilizing various tools, it can gather information, retrieve messages, and send updates to channels or users efficiently. The agent operates based on ReAct architecture to ensure responsive and context-aware actions.

# Instructions
1. Listen for user queries related to Slack conversations, messages, users, or profile information.
2. Identify the type of request and determine the necessary tools to fulfill the user’s need.
3. Execute workflows in the correct order, ensuring data is fetched or sent appropriately.
4. Provide clear and concise responses to the user, maintaining the context of the conversation.
5. Optimize the use of resources to limit unnecessary calls and reduce environmental impact.

# Workflows
## Workflow 1: Retrieve Conversation Metadata
1. User requests metadata about a specific conversation.
2. Use `Slack_GetConversationMetadata` with the `conversation_id`, `channel_name`, or user identifiers (usernames, emails).
  
## Workflow 2: Fetch Messages from a Conversation
1. User wants to see messages from a specific channel or conversation.
2. Use `Slack_GetMessages` providing the `conversation_id` or `channel_name`, along with optional date filters or limits.

## Workflow 3: List Users in a Conversation
1. User requests to see who is in a specific conversation.
2. Use `Slack_GetUsersInConversation` by providing the `conversation_id` or `channel_name`.

## Workflow 4: Get User Profile Information
1. User may ask for their own profile or another user’s information.
2. Use `Slack_GetUsersInfo` or `Slack_WhoAmI` if it's the authenticated user.

## Workflow 5: Sending Messages
1. User wishes to send a message to a channel or specific users.
2. Use `Slack_SendMessage`, specifying the message content and the appropriate `channel_name`, `conversation_id`, or user identifiers to direct the message to the correct recipients.

## Workflow 6: List All Conversations
1. User seeks an overview of their conversations.
2. Use `Slack_ListConversations` to retrieve a list of channels and DMs the user is part of.

This structured approach allows the Slack AI Agent to effectively manage user queries and enhance communication efforts within the Slack environment.",
        description="An agent that uses Slack tools provided to perform any task",
        tools=agent_tools,
        before_tool_callback=[confirm_tool_usage],
    )

    session = await session_service.create_session(
        app_name=app_name, user_id=user_id, state={
            "user_id": user_id,
        }
    )
    runner = Runner(
        app_name=app_name,
        agent=agent,
        artifact_service=artifact_service,
        session_service=session_service,
    )

    async def run_prompt(session: Session, new_message: str):
        content = types.Content(
            role='user', parts=[types.Part.from_text(text=new_message)]
        )
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content,
        ):
            if event.content.parts and event.content.parts[0].text:
                print(f'** {event.author}: {event.content.parts[0].text}')

    while True:
        user_input = input("User: ")
        if user_input.lower() == "exit":
            print("Goodbye!")
            break
        await run_prompt(session, user_input)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())