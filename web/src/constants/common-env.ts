const webConfig = {
    apiUrl: process.env.NODE_ENV === 'development' ? 'http://127.0.0.1:8000' : '',
    appVersion: process.env.NEXT_PUBLIC_APP_VERSION || '0.0.0',
    repositoryUrl: process.env.NEXT_PUBLIC_REPOSITORY_URL || '',
    releaseBaseUrl: (process.env.NEXT_PUBLIC_RELEASE_BASE_URL || '').replace(/\/$/, ''),
}

export default webConfig
