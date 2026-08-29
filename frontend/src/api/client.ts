import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 10_000,
})

export default client
