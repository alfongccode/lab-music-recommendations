import { post } from './http.js';

function getSimilarAudioTracks(formData, { signal } = {}) {
    return post('/api/search',
        formData,
        { signal }
    )
}

export {
    getSimilarAudioTracks
};