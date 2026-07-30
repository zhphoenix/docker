import { useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Square, Plus, MessageSquare } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { useChatStore } from '@/stores/chat-store'
import type { ChatMessage } from '@/stores/chat-store'
import { streamChatCompletion } from '@/services/chat'
import type { ChatRequestMessage } from '@/services/chat'

export default function ChatPage() {
  const {
    conversations,
    activeConversationId,
    isStreaming,
    createConversation,
    setActiveConversation,
    addMessage,
    updateMessage,
    setStreaming,
    getActiveConversation,
  } = useChatStore()

  const [input, setInput] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const activeConversation = getActiveConversation()

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  const handleSend = useCallback(async () => {
    const content = input.trim()
    if (!content || isStreaming) return

    let convId = activeConversationId
    if (!convId) {
      convId = createConversation()
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: Date.now(),
    }
    addMessage(convId, userMessage)
    setInput('')

    // Build messages history for API
    const conv = useChatStore.getState().conversations.find((c) => c.id === convId)
    const apiMessages: ChatRequestMessage[] = (conv?.messages ?? []).map((m) => ({
      role: m.role,
      content: m.content,
    }))

    const assistantMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      createdAt: Date.now(),
      streaming: true,
    }
    addMessage(convId, assistantMessage)
    setStreaming(true)

    const abortController = new AbortController()
    abortRef.current = abortController

    let accumulated = ''

    await streamChatCompletion({
      messages: apiMessages,
      signal: abortController.signal,
      onChunk: (chunk) => {
        accumulated += chunk
        updateMessage(convId!, assistantMessage.id, accumulated)
        requestAnimationFrame(scrollToBottom)
      },
      onDone: () => {
        setStreaming(false)
        abortRef.current = null
        scrollToBottom()
      },
      onError: (error) => {
        updateMessage(
          convId!,
          assistantMessage.id,
          accumulated || `错误: ${error.message}`
        )
        setStreaming(false)
        abortRef.current = null
      },
    })
  }, [
    input,
    isStreaming,
    activeConversationId,
    createConversation,
    addMessage,
    updateMessage,
    setStreaming,
    scrollToBottom,
  ])

  const handleStop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend]
  )

  return (
    <div className="flex h-full">
      {/* Conversation List */}
      <div className="flex w-64 shrink-0 flex-col border-r border-border">
        <div className="p-3">
          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            onClick={() => createConversation()}
          >
            <Plus className="size-4" />
            新对话
          </Button>
        </div>
        <ScrollArea className="flex-1">
          <div className="space-y-1 px-3 pb-3">
            {conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => setActiveConversation(conv.id)}
                className={cn(
                  'flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm transition-colors',
                  conv.id === activeConversationId
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-muted'
                )}
              >
                <MessageSquare className="size-4 shrink-0" strokeWidth={1.8} />
                <span className="truncate">{conv.title}</span>
              </button>
            ))}
            {conversations.length === 0 && (
              <p className="px-3 py-8 text-center text-xs text-muted-foreground">
                暂无对话
              </p>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Chat Area */}
      <div className="flex flex-1 flex-col">
        {/* Messages */}
        <ScrollArea className="flex-1">
          <div className="mx-auto max-w-3xl space-y-6 p-6">
            <AnimatePresence initial={false}>
              {activeConversation?.messages.map((msg) => (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className={cn(
                    'flex gap-3',
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  )}
                >
                  {msg.role === 'assistant' && (
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-xs font-bold text-primary-foreground">
                      AI
                    </div>
                  )}
                  <div
                    className={cn(
                      'max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
                      msg.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-card text-card-foreground border border-border'
                    )}
                  >
                    {msg.role === 'assistant' ? (
                      <div className="prose prose-sm dark:prose-invert max-w-none [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3 [&_code]:text-xs">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content || (msg.streaming ? '思考中...' : '')}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <span className="whitespace-pre-wrap">{msg.content}</span>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>

            {!activeConversation && (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <div className="flex size-16 items-center justify-center rounded-2xl bg-primary/10">
                  <MessageSquare className="size-8 text-primary" strokeWidth={1.5} />
                </div>
                <h2 className="mt-4 text-lg font-semibold text-foreground">
                  开始对话
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  输入问题，AI 助手将为你分析
                </p>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Input Area */}
        <div className="border-t border-border p-4">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end gap-3">
              <Textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                className="min-h-[44px] max-h-[160px] flex-1 resize-none rounded-xl"
                rows={1}
              />
              {isStreaming ? (
                <Button
                  size="icon"
                  variant="destructive"
                  className="size-11 shrink-0 rounded-xl"
                  onClick={handleStop}
                >
                  <Square className="size-4" />
                </Button>
              ) : (
                <Button
                  size="icon"
                  className="size-11 shrink-0 rounded-xl"
                  onClick={handleSend}
                  disabled={!input.trim()}
                >
                  <Send className="size-4" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
