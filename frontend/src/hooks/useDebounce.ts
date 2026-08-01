import { useEffect, useState } from 'react'

/**
 * 对频繁变化的值进行防抖，延迟 delay 毫秒后才更新返回值。
 * 典型场景：搜索输入框 -> API 请求
 */
export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}
