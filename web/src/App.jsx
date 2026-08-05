import React, { useCallback, useState } from 'react';
import './App.css';
import { getSimilarAudioTracks } from './providers'

const STATIC_AUDIO_DIR = "tinyAAM/audio-mixes-mp3"

export default function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [recomendations, setRecomendations] = useState([]);
  const [status, setStatus] = useState('idle');

  const handleFileChange = (event) => {
    if (event.target.files.length > 0) {
      setSelectedFile(event.target.files[0]);
    }
  };

  const handleSubmit = useCallback(async (event) => {
    event.preventDefault();
    const controller = new AbortController();

    console.log(selectedFile)
    if (!selectedFile) {
      alert('Please, choose an audio track.');
      return;
    }

    setStatus('loading');

    const formData = new FormData();

    formData.append('audioTrack', selectedFile);

    try {
      const response = await getSimilarAudioTracks(formData, { signal: controller?.signal });

      setRecomendations(response);

      setStatus('idle');
    } catch (error) {
      console.error('Error sending audio track:', error);
      setStatus('error');
    }
    return () => controller.abort()
  }, [selectedFile]);

  return (
    <div className="app-container">

      <header className="app-header">
        <div className="app-logo" aria-hidden="true">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M9 18V5l12-2v13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <circle cx="6" cy="18" r="3" stroke="currentColor" strokeWidth="2"/>
            <circle cx="18" cy="16" r="3" stroke="currentColor" strokeWidth="2"/>
          </svg>
        </div>
        <h1 className="app-title">Music Finder</h1>
        <p className="app-subtitle">
          Upload an audio track and discover songs similar to your taste
        </p>
      </header>

      <form onSubmit={handleSubmit}>
        <label htmlFor="audioFile" className="upload-label">
          Upload an audio file to find similar songs
        </label>

        <label htmlFor="audioFile" className="dropzone">
          <svg className="dropzone-icon" width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 16V4m0 0L8 8m4-4l4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <span className="dropzone-text">
            {selectedFile ? selectedFile.name : 'Click to choose an MP3 file'}
          </span>
          <span className="dropzone-hint">
            {selectedFile
              ? `${Math.round(selectedFile.size / 1024)} KB`
              : 'MP3 · audio/mpeg'}
          </span>
          <input
            type="file"
            id="audioFile"
            accept="audio/mpeg, audio/mp3"
            onChange={handleFileChange}
            required
            className="file-input"
          />
        </label>

        {selectedFile && (
          <div className="file-description">
            <audio id="selectedTrack" src={URL.createObjectURL(selectedFile)} controls></audio>
          </div>
        )}

        <button
          type="submit"
          disabled={status === 'loading'}
          className="file-submit"
        >
          {status === 'loading' ? (
            <>
              <span className="spinner" aria-hidden="true"></span>
              Searching for similar tracks...
            </>
          ) : (
            'Search for similar tracks'
          )}
        </button>
      </form>

      {status === 'error' && (
        <p className="status-message status-error">
          Something went wrong. Please try again.
        </p>
      )}

      {status === 'loading' && (
        <div className="results-loading">
          <span className="spinner spinner-lg" aria-hidden="true"></span>
          <span>Analyzing your audio...</span>
        </div>
      )}

      {status === 'idle' && recomendations && recomendations.length > 0 && (
        <section className="results">
          <h2 className="results-title">Similar tracks</h2>
          <ul>{recomendations.map((recomendation, index) =>
            <li key={index}>
              <div className="track-info">
                <span className="track-name">{recomendation?.filename}</span>
                <span className="track-score">score: {recomendation?.score}</span>
              </div>
              <audio id="recomendedTrack" src={`${STATIC_AUDIO_DIR}/${recomendation?.filename}`} controls></audio>
            </li>
          )}</ul>
        </section>
      )}
    </div>
  );
}