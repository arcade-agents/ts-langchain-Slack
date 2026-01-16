from agents import (Agent, Runner, AgentHooks, Tool, RunContextWrapper,
                    TResponseInputItem,)
from functools import partial
from arcadepy import AsyncArcade
from agents_arcade import get_arcade_tools
from typing import Any
from human_in_the_loop import (UserDeniedToolCall,
                               confirm_tool_usage,
                               auth_tool)

import globals


class CustomAgentHooks(AgentHooks):
    def __init__(self, display_name: str):
        self.event_counter = 0
        self.display_name = display_name

    async def on_start(self,
                       context: RunContextWrapper,
                       agent: Agent) -> None:
        self.event_counter += 1
        print(f"### ({self.display_name}) {
              self.event_counter}: Agent {agent.name} started")

    async def on_end(self,
                     context: RunContextWrapper,
                     agent: Agent,
                     output: Any) -> None:
        self.event_counter += 1
        print(
            f"### ({self.display_name}) {self.event_counter}: Agent {
                # agent.name} ended with output {output}"
                agent.name} ended"
        )

    async def on_handoff(self,
                         context: RunContextWrapper,
                         agent: Agent,
                         source: Agent) -> None:
        self.event_counter += 1
        print(
            f"### ({self.display_name}) {self.event_counter}: Agent {
                source.name} handed off to {agent.name}"
        )

    async def on_tool_start(self,
                            context: RunContextWrapper,
                            agent: Agent,
                            tool: Tool) -> None:
        self.event_counter += 1
        print(
            f"### ({self.display_name}) {self.event_counter}:"
            f" Agent {agent.name} started tool {tool.name}"
            f" with context: {context.context}"
        )

    async def on_tool_end(self,
                          context: RunContextWrapper,
                          agent: Agent,
                          tool: Tool,
                          result: str) -> None:
        self.event_counter += 1
        print(
            f"### ({self.display_name}) {self.event_counter}: Agent {
                # agent.name} ended tool {tool.name} with result {result}"
                agent.name} ended tool {tool.name}"
        )


async def main():

    context = {
        "user_id": os.getenv("ARCADE_USER_ID"),
    }

    client = AsyncArcade()

    arcade_tools = await get_arcade_tools(
        client, toolkits=["Slack"]
    )

    for tool in arcade_tools:
        # - human in the loop
        if tool.name in ENFORCE_HUMAN_CONFIRMATION:
            tool.on_invoke_tool = partial(
                confirm_tool_usage,
                tool_name=tool.name,
                callback=tool.on_invoke_tool,
            )
        # - auth
        await auth_tool(client, tool.name, user_id=context["user_id"])

    agent = Agent(
        name="",
        instructions="# Introduction
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
        model=os.environ["OPENAI_MODEL"],
        tools=arcade_tools,
        hooks=CustomAgentHooks(display_name="")
    )

    # initialize the conversation
    history: list[TResponseInputItem] = []
    # run the loop!
    while True:
        prompt = input("You: ")
        if prompt.lower() == "exit":
            break
        history.append({"role": "user", "content": prompt})
        try:
            result = await Runner.run(
                starting_agent=agent,
                input=history,
                context=context
            )
            history = result.to_input_list()
            print(result.final_output)
        except UserDeniedToolCall as e:
            history.extend([
                {"role": "assistant",
                 "content": f"Please confirm the call to {e.tool_name}"},
                {"role": "user",
                 "content": "I changed my mind, please don't do it!"},
                {"role": "assistant",
                 "content": f"Sure, I cancelled the call to {e.tool_name}."
                 " What else can I do for you today?"
                 },
            ])
            print(history[-1]["content"])

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())