"""Line-oriented terminal chat presentation."""

from reprobe.chat.commands import ChatModel, GenerateChatReply


def chat(model: ChatModel) -> None:
    history = ()
    print("Chat ready. Use /clear to reset history, /exit or /quit to leave.")
    while True:
        try:
            user_input = input("You: ")
        except EOFError:
            print()
            return
        action = user_input.strip()
        if action in {"/exit", "/quit"}:
            return
        if action == "/clear":
            history = ()
            print("History cleared.")
            continue
        if not action:
            continue
        turn = GenerateChatReply(model, history, user_input).execute()
        history = turn.history
        print(f"Assistant: {turn.reply.content}")
        if turn.reply.finish_reason == "length":
            print("[Reply reached the token limit.]")
