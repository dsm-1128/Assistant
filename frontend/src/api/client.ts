import axios, { AxiosError } from 'axios'

import type { StatusResponse, TaskResponse, TravelRequest } from './types'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 150_000,
})

export async function submitGuide(payload: TravelRequest): Promise<string> {
  const response = await api.post<{ task_id: string }>('/guides', payload)
  return response.data.task_id
}

export async function fetchTask(taskId: string): Promise<TaskResponse> {
  const response = await api.get<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}`)
  return response.data
}

export async function uploadKnowledge(form: FormData) {
  const response = await api.post<{ files: number; chunks: number; message: string }>(
    '/knowledge/documents',
    form,
  )
  return response.data
}

export async function fetchStatus(): Promise<StatusResponse> {
  const response = await api.get<StatusResponse>('/status')
  return response.data
}

export function readableError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const payload = (error as AxiosError<{ error?: { message?: string } }>).response?.data
    return payload?.error?.message || error.message || '请求失败，请稍后重试。'
  }
  return error instanceof Error ? error.message : '发生未知错误，请稍后重试。'
}

export function responseStatus(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined
}
