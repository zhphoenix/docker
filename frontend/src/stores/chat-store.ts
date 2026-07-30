import { create } from 'zustand'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  createdAt: number
  streaming?: boolean
}

export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: number
}

interface ChatState {
  conversations: Conversation[]
  activeConversationId: string | null
  isStreaming: boolean

  createConversation: () => string
  setActiveConversation: (id: string) => void
  addMessage: (conversationId: string, message: ChatMessage) => void
  updateMessage: (conversationId: string, messageId: string, content: string) => void
  setStreaming: (streaming: boolean) => void
  getActiveConversation: () => Conversation | undefined
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  isStreaming: false,

  createConversation: () => {
    const id = crypto.randomUUID()
    const conversation: Conversation = {
      id,
      title: '新对话',
      messages: [],
      createdAt: Date.now(),
    }
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      activeConversationId: id,
    }))
    return id
  },

  setActiveConversation: (id) => set({ activeConversationId: id }),

  addMessage: (conversationId, message) =>
    set((state) => ({
      conversations: state.conversations.map((conv) =>
        conv.id === conversationId
          ? {
              ...conv,
              messages: [...conv.messages, message],
              title:
                conv.messages.length === 0 && message.role === 'user'
                  ? message.content.slice(0, 30) || '新对话'
                  : conv.title,
            }
          : conv
      ),
    })),

  updateMessage: (conversationId, messageId, content) =>
    set((state) => ({
      conversations: state.conversations.map((conv) =>
        conv.id === conversationId
          ? {
              ...conv,
              messages: conv.messages.map((msg) =>
                msg.id === messageId ? { ...msg, content } : msg
              ),
            }
          : conv
      ),
    })),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  getActiveConversation: () => {
    const { conversations, activeConversationId } = get()
    return conversations.find((c) => c.id === activeConversationId)
  },
}))
