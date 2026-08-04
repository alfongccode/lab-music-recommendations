import React, { useCallback, useState } from 'react';
import { getSimilarAudioTracks } from './providers'

export default function MultipartForm() {
  const [selectedFile, setSelectedFile] = useState(null);
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
      alert('Por favor, selecciona un archivo.');
      return;
    }

    setStatus('loading');

    const formData = new FormData();
    
    formData.append('audioTrack', selectedFile);

    try {
      const response = await getSimilarAudioTracks(formData, { signal: controller?.signal });

    } catch (error) {
      console.error('Error sending audio track:', error);
      setStatus('error');
    }
    return () => controller.abort()
  }, [selectedFile]);

  return (
    <div className="app-container">
      
      <form onSubmit={handleSubmit}>
        <div className="form-container">
          <label htmlFor="audioFile">Upload an audio file to find songs similar to your tastes</label>
          <input
            type="file"
            id="audioFile"
            accept="audio/mpeg, audio/mp3"
            onChange={handleFileChange}
            required
            className="file-input"
          />
        </div>

        {selectedFile && (
          <div className="file-description">
            Audio track: {selectedFile.name} ({Math.round(selectedFile.size / 1024)} KB)
          </div>
        )}

        {/* Botón de envío */}
        <button 
          type="submit" 
          disabled={status === 'loading'}
          className="file-submit"
        >
          {status === 'loading' ? 'Searching for similar audio tracks...' : ''}
        </button>
      </form>
    </div>
  );
}