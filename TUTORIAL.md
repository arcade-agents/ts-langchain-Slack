---
title: "Build a Slack agent with LangChain (TypeScript) and Arcade"
slug: "ts-langchain-Slack"
framework: "langchain-ts"
language: "typescript"
toolkits: ["Slack"]
tools: []
difficulty: "beginner"
generated_at: "2026-03-12T01:34:47Z"
source_template: "ts_langchain"
agent_repo: ""
tags:
  - "langchain"
  - "typescript"
  - "slack"
---

# Build a Slack agent with LangChain (TypeScript) and Arcade

In this tutorial you'll build an AI agent using [LangChain](https://js.langchain.com/) with [LangGraph](https://langchain-ai.github.io/langgraphjs/) in TypeScript and [Arcade](https://arcade.dev) that can interact with Slack tools — with built-in authorization and human-in-the-loop support.

## Prerequisites

- The [Bun](https://bun.com) runtime
- An [Arcade](https://arcade.dev) account and API key
- An OpenAI API key

## Project Setup

First, create a directory for this project, and install all the required dependencies:

````bash
mkdir slack-agent && cd slack-agent
bun install @arcadeai/arcadejs @langchain/langgraph @langchain/core langchain chalk
````

## Start the agent script

Create a `main.ts` script, and import all the packages and libraries. Imports from 
the `"./tools"` package may give errors in your IDE now, but don't worry about those
for now, you will write that helper package later.

````typescript
"use strict";
import { getTools, confirm, arcade } from "./tools";
import { createAgent } from "langchain";
import {
  Command,
  MemorySaver,
  type Interrupt,
} from "@langchain/langgraph";
import chalk from "chalk";
import * as readline from "node:readline/promises";
````

## Configuration

In `main.ts`, configure your agent's toolkits, system prompt, and model. Notice
how the system prompt tells the agent how to navigate different scenarios and
how to combine tool usage in specific ways. This prompt engineering is important
to build effective agents. In fact, the more agentic your application, the more
relevant the system prompt to truly make the agent useful and effective at
using the tools at its disposal.

````typescript
// configure your own values to customize your agent

// The Arcade User ID identifies who is authorizing each service.
const arcadeUserID = process.env.ARCADE_USER_ID;
if (!arcadeUserID) {
  throw new Error("Missing ARCADE_USER_ID. Add it to your .env file.");
}
// This determines which MCP server is providing the tools, you can customize this to make a Slack agent, or Notion agent, etc.
// all tools from each of these MCP servers will be retrieved from arcade
const toolkits=['Slack'];
// This determines isolated tools that will be
const isolatedTools=[];
// This determines the maximum number of tool definitions Arcade will return
const toolLimit = 100;
// This prompt defines the behavior of the agent.
const systemPrompt = "# Slack ReAct Agent \u2014 Prompt\n\n## Introduction\nYou are a ReAct-style AI agent that helps users interact with Slack using a small set of tools (list, metadata, messages, users, send message, whoami). Your job is to satisfy user requests about conversations, messages, and users in Slack by selecting and calling the right tools, combining results, and returning clear, actionable responses. Use the ReAct loop: think, act (call a tool), observe the tool output, and iterate until you have a final answer or need clarification.\n\n---\n\n## Instructions (how you should behave)\n- Always follow the ReAct format in your reasoning logs:\n  - Thought: (your reasoning \u2014 should be short)\n  - Action: (the tool you call and exact parameters)\n  - Observation: (the result returned by the tool)\n  - (repeat until ready) then Final Answer: (what you tell the user)\n- Be parsimonious with tool calls. Do not call a tool unless it is necessary to complete the user\u2019s request.\n- Use the tool-specific constraints:\n  - Provide exactly one of mutually-exclusive identifiers when required (e.g., conversation_id OR channel_name OR user identifiers).\n  - Respect pagination and limits (List/Message defaults and maxes).\n  - Do not call Slack_GetUsersInfo multiple times \u2014 batch user_ids/usernames/emails in one call.\n- Prefer conversation_id over channel_name for performance whenever possible.\n- Use date filtering when requesting messages to reduce payload and work (oldest_datetime/latest_datetime or oldest_relative/latest_relative, but do not mix absolute and relative).\n- When fetching users for a conversation, prefer Slack_GetUsersInConversation to get user IDs, then call Slack_GetUsersInfo once with all needed IDs if you need profile details.\n- If a tool returns an error, include the error text in your observation and ask the user a clarifying question if necessary.\n- Protect privacy and security: do not log or display tokens/credentials and avoid exposing unnecessary PII. When summarizing messages, redact or ask before exposing private or sensitive content.\n- If unsure what the user wants, ask a clarifying question before calling tools.\n\n---\n\n## ReAct Response Template (always follow)\nWhen you interact with tools and produce intermediary reasoning, use this structure:\n\nThought: [short reasoning about next step]  \nAction: Call ToolName with params:\n```\nToolName(param_name1=value1, param_name2=value2, ...)\n```\nObservation: [tool output or error]\n\n...repeat until ready...\n\nFinal Answer: [user-facing answer, summary, or next steps]\n\n---\n\n## Workflows\nBelow are common workflows and the recommended sequence of tool calls and handling notes.\n\n1) Inspect a channel/DM (existence, topic, purpose)\n- Purpose: Confirm the conversation exists and get basic metadata.\n- Sequence:\n  1. Slack_GetConversationMetadata (prefer conversation_id; otherwise channel_name or user_ids/usernames/emails)\n  2. If user list needed: Slack_GetUsersInConversation (conversation_id)\n  3. If user profile details needed: Slack_GetUsersInfo (single call with all user_ids)\n- Notes: Use metadata to determine if it\u2019s a channel/DM/MPIM and whether the bot/user is a member.\n\nExample:\n```\nThought: Check whether #engineering exists and human-readable metadata.\nAction: Slack_GetConversationMetadata(channel_name=\"engineering\")\nObservation: {...}\nFinal Answer: The channel exists; topic is \"Sprint planning\", member_count=42. Do you want recent messages?\n```\n\n2) Read recent messages from a conversation and summarize\n- Purpose: Retrieve and summarize recent posts.\n- Sequence:\n  1. Slack_GetConversationMetadata (optional, to confirm conversation_id and type)\n  2. Slack_GetMessages with conversation_id OR channel_name OR user identifiers. Use date filters (oldest_relative or oldest_datetime) and limit to reduce volume (limit \u003c= 100).\n  3. If you need authors\u2019 full profiles: Slack_GetUsersInConversation (conversation_id) \u2192 Slack_GetUsersInfo (one call with all user_ids).\n  4. Summarize results for the user, redact PII if required, and propose follow-ups.\n- Pagination: If the message volume exceeds the limit, use next_cursor to page. Stop when you have enough context or have processed required pages.\n\nExample:\n```\nThought: Retrieve last 48 hours of messages from conversation X.\nAction: Slack_GetMessages(conversation_id=\"C12345\", oldest_relative=\"02:00:00\", limit=100)\nObservation: {... messages ..., next_cursor: \"abc\"}\nThought: There is more\u2014either page or stop if summary is sufficient.\n```\n\n3) Find messages that match a query (e.g., \"deployment\", \"invoice\")\n- Purpose: Narrow search to relevant timeframe and summarize hits.\n- Sequence:\n  1. Ask clarifying question if query or timeframe is missing.\n  2. Slack_GetMessages with suitable oldest_datetime/latest_datetime or oldest_relative and a small limit; filter client-side by text matches (the tool returns raw messages).\n  3. If needed, fetch user info for the matched message authors in one Slack_GetUsersInfo call.\n- Notes: Slack_GetMessages does not support server-side text search in these tools \u2014 the agent filters results client-side.\n\n4) List conversations the user is in\n- Purpose: Provide a list of channels/DMs/MPIMs the agent user is in.\n- Sequence:\n  1. Slack_ListConversations(conversation_types=[...]) \u2014 optionally filter by type and page using next_cursor.\n  2. Summarize and ask which conversation to inspect next.\n- Notes: Use limit and next_cursor for large orgs.\n\n5) Get users in a conversation and show profiles\n- Purpose: Show members and their profile info.\n- Sequence:\n  1. Slack_GetUsersInConversation(conversation_id=...)\n  2. Slack_GetUsersInfo(user_ids=[...]) \u2014 one batch call with all user_ids you need\n- Important: Do not call Slack_GetUsersInfo multiple times for the same request. Batch the user IDs.\n\n6) Send a message to a channel or user(s)\n- Purpose: Post content to a conversation or DM a set of users.\n- Sequence:\n  1. Confirm exact target(s) with the user (channel_name vs conversation_id vs user_ids/usernames/emails). You must provide exactly one of channel_name, conversation_id, or user identifiers as per the tool.\n  2. Slack_SendMessage(message=\"...\", conversation_id=\"...\" OR channel_name=\"...\" OR user_ids=[...])\n  3. Observe success/failure and report back.\n- Safety: Confirm content before sending if it could be sensitive or if formatted with mentions, attachments, or actions.\n\nExample:\n```\nThought: Send reminder to #eng-team about the retro.\nAction: Slack_SendMessage(channel_name=\"eng-team\", message=\"Reminder: retro at 3pm today. Please add topics.\")\nObservation: {\"ok\": true, \"ts\": \"1612345678.000200\"}\nFinal Answer: Reminder posted to #eng-team at 3pm.\n```\n\n7) Who am I (agent identity)\n- Purpose: Retrieve the authenticated bot/user info.\n- Sequence:\n  1. Slack_WhoAmI()\n  2. Return profile (name, email, id, etc.) to the user, but do not reveal credentials.\n- Notes: Useful for confirming which Slack identity will send messages.\n\n---\n\n## Tool-Calling Examples (format to use)\nCall a tool with this exact code-block style. Replace values as appropriate.\n\n- Get conversation metadata:\n```\nAction: Slack_GetConversationMetadata(conversation_id=\"C1234567890\")\n```\n\n- Get messages (last 3 days, up to 100 messages):\n```\nAction: Slack_GetMessages(conversation_id=\"C1234567890\", oldest_relative=\"03:00:00\", limit=100)\n```\n(Format for oldest_relative is \"DD:HH:MM\" \u2014 for 3 days use \"03:00:00\".)\n\n- Get users in conversation:\n```\nAction: Slack_GetUsersInConversation(conversation_id=\"C1234567890\", limit=200)\n```\n\n- Get user info for multiple users (single batch call):\n```\nAction: Slack_GetUsersInfo(user_ids=[\"U111\",\"U222\",\"U333\"])\n```\n\n- Send a message to a channel:\n```\nAction: Slack_SendMessage(conversation_id=\"C1234567890\", message=\"Standup in 10 minutes. Please join.\")\n```\n\n- Who am I:\n```\nAction: Slack_WhoAmI()\n```\n\n---\n\n## Best Practices \u0026 Edge Cases\n- Efficiency: Avoid Slack_ListUsers or Slack_GetUsersInfo unless you need full user profiles; instead, use conversation-level tools (GetConversationMetadata, GetMessages) which accept user identifiers directly.\n- CO2 \u0026 Rate Limits: Batch calls; don\u2019t call the same tool repeatedly for the same data. The Slack_GetUsersInfo tool warns explicitly: if you need multiple users, fetch them in one call.\n- Pagination: Check for next_cursor in list/message responses. Only page if you need more results.\n- Ambiguity: If the user doesn\u2019t specify channel vs DM vs user list, ask a clarifying question before calling tools.\n- Error handling: If a tool returns an error, include the error text in Observation and propose next steps (retry, clarify, or escalate).\n- Privacy: Redact or request permission before revealing or sending sensitive message content or PII.\n- Final responses to users should be a human-friendly summary or action confirmation \u2014 do not dump raw JSON unless the user requests it.\n\n---\n\nIf you understand, start by asking the user what they want to do or by clarifying missing details (conversation id vs channel name vs user emails). Use the ReAct template for every step and follow the workflows above.";
// This determines which LLM will be used inside the agent
const agentModel = process.env.OPENAI_MODEL;
if (!agentModel) {
  throw new Error("Missing OPENAI_MODEL. Add it to your .env file.");
}
// This allows LangChain to retain the context of the session
const threadID = "1";
````

Set the following environment variables in a `.env` file:

````bash
ARCADE_API_KEY=your-arcade-api-key
ARCADE_USER_ID=your-arcade-user-id
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-5-mini
````

## Implementing the `tools.ts` module

The `tools.ts` module fetches Arcade tool definitions and converts them to LangChain-compatible tools using Arcade's Zod schema conversion:

### Create the file and import the dependencies

Create a `tools.ts` file, and add import the following. These will allow you to build the helper functions needed to convert Arcade tool definitions into a format that LangChain can execute. Here, you also define which tools will require human-in-the-loop confirmation. This is very useful for tools that may have dangerous or undesired side-effects if the LLM hallucinates the values in the parameters. You will implement the helper functions to require human approval in this module.

````typescript
import { Arcade } from "@arcadeai/arcadejs";
import {
  type ToolExecuteFunctionFactoryInput,
  type ZodTool,
  executeZodTool,
  isAuthorizationRequiredError,
  toZod,
} from "@arcadeai/arcadejs/lib/index";
import { type ToolExecuteFunction } from "@arcadeai/arcadejs/lib/zod/types";
import { tool } from "langchain";
import {
  interrupt,
} from "@langchain/langgraph";
import readline from "node:readline/promises";

// This determines which tools require human in the loop approval to run
const TOOLS_WITH_APPROVAL = ['Slack_GetConversationMetadata', 'Slack_GetMessages', 'Slack_GetUsersInConversation', 'Slack_GetUsersInfo', 'Slack_ListConversations', 'Slack_ListUsers', 'Slack_SendMessage'];
````

### Create a confirmation helper for human in the loop

The first helper that you will write is the `confirm` function, which asks a yes or no question to the user, and returns `true` if theuser replied with `"yes"` and `false` otherwise.

````typescript
// Prompt user for yes/no confirmation
export async function confirm(question: string, rl?: readline.Interface): Promise<boolean> {
  let shouldClose = false;
  let interface_ = rl;

  if (!interface_) {
      interface_ = readline.createInterface({
          input: process.stdin,
          output: process.stdout,
      });
      shouldClose = true;
  }

  const answer = await interface_.question(`${question} (y/n): `);

  if (shouldClose) {
      interface_.close();
  }

  return ["y", "yes"].includes(answer.trim().toLowerCase());
}
````

Tools that require authorization trigger a LangGraph interrupt, which pauses execution until the user completes authorization in their browser.

### Create the execution helper

This is a wrapper around the `executeZodTool` function. Before you execute the tool, however, there are two logical checks to be made:

1. First, if the tool the agent wants to invoke is included in the `TOOLS_WITH_APPROVAL` variable, human-in-the-loop is enforced by calling `interrupt` and passing the necessary data to call the `confirm` helper. LangChain will surface that `interrupt` to the agentic loop, and you will be required to "resolve" the interrupt later on. For now, you can assume that the reponse of the `interrupt` will have enough information to decide whether to execute the tool or not, depending on the human's reponse.
2. Second, if the tool was approved by the human, but it doesn't have the authorization of the integration to run, then you need to present an URL to the user so they can authorize the OAuth flow for this operation. For this, an execution is attempted, that may fail to run if the user is not authorized. When it fails, you interrupt the flow and send the authorization request for the harness to handle. If the user authorizes the tool, the harness will reply with an `{authorized: true}` object, and the system will retry the tool call without interrupting the flow.

````typescript
export function executeOrInterruptTool({
  zodToolSchema,
  toolDefinition,
  client,
  userId,
}: ToolExecuteFunctionFactoryInput): ToolExecuteFunction<any> {
  const { name: toolName } = zodToolSchema;

  return async (input: unknown) => {
    try {

      // If the tool is on the list that enforces human in the loop, we interrupt the flow and ask the user to authorize the tool

      if (TOOLS_WITH_APPROVAL.includes(toolName)) {
        const hitl_response = interrupt({
          authorization_required: false,
          hitl_required: true,
          tool_name: toolName,
          input: input,
        });

        if (!hitl_response.authorized) {
          // If the user didn't approve the tool call, we throw an error, which will be handled by LangChain
          throw new Error(
            `Human in the loop required for tool call ${toolName}, but user didn't approve.`
          );
        }
      }

      // Try to execute the tool
      const result = await executeZodTool({
        zodToolSchema,
        toolDefinition,
        client,
        userId,
      })(input);
      return result;
    } catch (error) {
      // If the tool requires authorization, we interrupt the flow and ask the user to authorize the tool
      if (error instanceof Error && isAuthorizationRequiredError(error)) {
        const response = await client.tools.authorize({
          tool_name: toolName,
          user_id: userId,
        });

        // We interrupt the flow here, and pass everything the handler needs to get the user's authorization
        const interrupt_response = interrupt({
          authorization_required: true,
          authorization_response: response,
          tool_name: toolName,
          url: response.url ?? "",
        });

        // If the user authorized the tool, we retry the tool call without interrupting the flow
        if (interrupt_response.authorized) {
          const result = await executeZodTool({
            zodToolSchema,
            toolDefinition,
            client,
            userId,
          })(input);
          return result;
        } else {
          // If the user didn't authorize the tool, we throw an error, which will be handled by LangChain
          throw new Error(
            `Authorization required for tool call ${toolName}, but user didn't authorize.`
          );
        }
      }
      throw error;
    }
  };
}
````

### Create the tool retrieval helper

The last helper function of this module is the `getTools` helper. This function will take the configurations you defined in the `main.ts` file, and retrieve all of the configured tool definitions from Arcade. Those definitions will then be converted to LangGraph `Function` tools, and will be returned in a format that LangChain can present to the LLM so it can use the tools and pass the arguments correctly. You will pass the `executeOrInterruptTool` helper you wrote in the previous section so all the bindings to the human-in-the-loop and auth handling are programmed when LancChain invokes a tool.


````typescript
// Initialize the Arcade client
export const arcade = new Arcade();

export type GetToolsProps = {
  arcade: Arcade;
  toolkits?: string[];
  tools?: string[];
  userId: string;
  limit?: number;
}


export async function getTools({
  arcade,
  toolkits = [],
  tools = [],
  userId,
  limit = 100,
}: GetToolsProps) {

  if (toolkits.length === 0 && tools.length === 0) {
      throw new Error("At least one tool or toolkit must be provided");
  }

  // Todo(Mateo): Add pagination support
  const from_toolkits = await Promise.all(toolkits.map(async (tkitName) => {
      const definitions = await arcade.tools.list({
          toolkit: tkitName,
          limit: limit
      });
      return definitions.items;
  }));

  const from_tools = await Promise.all(tools.map(async (toolName) => {
      return await arcade.tools.get(toolName);
  }));

  const all_tools = [...from_toolkits.flat(), ...from_tools];
  const unique_tools = Array.from(
      new Map(all_tools.map(tool => [tool.qualified_name, tool])).values()
  );

  const arcadeTools = toZod({
    tools: unique_tools,
    client: arcade,
    executeFactory: executeOrInterruptTool,
    userId: userId,
  });

  // Convert Arcade tools to LangGraph tools
  const langchainTools = arcadeTools.map(({ name, description, execute, parameters }) =>
    (tool as Function)(execute, {
      name,
      description,
      schema: parameters,
    })
  );

  return langchainTools;
}
````

## Building the Agent

Back on the `main.ts` file, you can now call the helper functions you wrote to build the agent.

### Retrieve the configured tools

Use the `getTools` helper you wrote to retrieve the tools from Arcade in LangChain format:

````typescript
const tools = await getTools({
  arcade,
  toolkits: toolkits,
  tools: isolatedTools,
  userId: arcadeUserID,
  limit: toolLimit,
});
````

### Write an interrupt handler

When LangChain is interrupted, it will emit an event in the stream that you will need to handle and resolve based on the user's behavior. For a human-in-the-loop interrupt, you will call the `confirm` helper you wrote earlier, and indicate to the harness whether the human approved the specific tool call or not. For an auth interrupt, you will present the OAuth URL to the user, and wait for them to finishe the OAuth dance before resolving the interrupt with `{authorized: true}` or `{authorized: false}` if an error occurred:

````typescript
async function handleInterrupt(
  interrupt: Interrupt,
  rl: readline.Interface
): Promise<{ authorized: boolean }> {
  const value = interrupt.value;
  const authorization_required = value.authorization_required;
  const hitl_required = value.hitl_required;
  if (authorization_required) {
    const tool_name = value.tool_name;
    const authorization_response = value.authorization_response;
    console.log("⚙️: Authorization required for tool call", tool_name);
    console.log(
      "⚙️: Please authorize in your browser",
      authorization_response.url
    );
    console.log("⚙️: Waiting for you to complete authorization...");
    try {
      await arcade.auth.waitForCompletion(authorization_response.id);
      console.log("⚙️: Authorization granted. Resuming execution...");
      return { authorized: true };
    } catch (error) {
      console.error("⚙️: Error waiting for authorization to complete:", error);
      return { authorized: false };
    }
  } else if (hitl_required) {
    console.log("⚙️: Human in the loop required for tool call", value.tool_name);
    console.log("⚙️: Please approve the tool call", value.input);
    const approved = await confirm("Do you approve this tool call?", rl);
    return { authorized: approved };
  }
  return { authorized: false };
}
````

### Create an Agent instance

Here you create the agent using the `createAgent` function. You pass the system prompt, the model, the tools, and the checkpointer. When the agent runs, it will automatically use the helper function you wrote earlier to handle tool calls and authorization requests.

````typescript
const agent = createAgent({
  systemPrompt: systemPrompt,
  model: agentModel,
  tools: tools,
  checkpointer: new MemorySaver(),
});
````

### Write the invoke helper

This last helper function handles the streaming of the agent’s response, and captures the interrupts. When the system detects an interrupt, it adds the interrupt to the `interrupts` array, and the flow interrupts. If there are no interrupts, it will just stream the agent’s to your console.

````typescript
async function streamAgent(
  agent: any,
  input: any,
  config: any
): Promise<Interrupt[]> {
  const stream = await agent.stream(input, {
    ...config,
    streamMode: "updates",
  });
  const interrupts: Interrupt[] = [];

  for await (const chunk of stream) {
    if (chunk.__interrupt__) {
      interrupts.push(...(chunk.__interrupt__ as Interrupt[]));
      continue;
    }
    for (const update of Object.values(chunk)) {
      for (const msg of (update as any)?.messages ?? []) {
        console.log("🤖: ", msg.toFormattedString());
      }
    }
  }

  return interrupts;
}
````

### Write the main function

Finally, write the main function that will call the agent and handle the user input.

Here the `config` object configures the `thread_id`, which tells the agent to store the state of the conversation into that specific thread. Like any typical agent loop, you:

1. Capture the user input
2. Stream the agent's response
3. Handle any authorization interrupts
4. Resume the agent after authorization
5. Handle any errors
6. Exit the loop if the user wants to quit

````typescript
async function main() {
  const config = { configurable: { thread_id: threadID } };
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  console.log(chalk.green("Welcome to the chatbot! Type 'exit' to quit."));
  while (true) {
    const input = await rl.question("> ");
    if (input.toLowerCase() === "exit") {
      break;
    }
    rl.pause();

    try {
      let agentInput: any = {
        messages: [{ role: "user", content: input }],
      };

      // Loop until no more interrupts
      while (true) {
        const interrupts = await streamAgent(agent, agentInput, config);

        if (interrupts.length === 0) {
          break; // No more interrupts, we're done
        }

        // Handle all interrupts
        const decisions: any[] = [];
        for (const interrupt of interrupts) {
          decisions.push(await handleInterrupt(interrupt, rl));
        }

        // Resume with decisions, then loop to check for more interrupts
        // Pass single decision directly, or array for multiple interrupts
        agentInput = new Command({ resume: decisions.length === 1 ? decisions[0] : decisions });
      }
    } catch (error) {
      console.error(error);
    }

    rl.resume();
  }
  console.log(chalk.red("👋 Bye..."));
  process.exit(0);
}

// Run the main function
main().catch((err) => console.error(err));
````

## Running the Agent

### Run the agent

```bash
bun run main.ts
```

You should see the agent responding to your prompts like any model, as well as handling any tool calls and authorization requests.

## Next Steps

- Clone the [repository](https://github.com/arcade-agents/ts-langchain-Slack) and run it
- Add more toolkits to the `toolkits` array to expand capabilities
- Customize the `systemPrompt` to specialize the agent's behavior
- Explore the [Arcade documentation](https://docs.arcade.dev) for available toolkits

