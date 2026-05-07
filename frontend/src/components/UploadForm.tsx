import { type FormEvent, useCallback, useState } from 'react';
import type { FileRejection } from 'react-dropzone';
import { useDropzone } from 'react-dropzone';
import type { ApiError } from '../api/client';

interface UploadFormProps {
  onSubmit: (formData: FormData) => void;
  isLoading: boolean;
  error: ApiError | null;
}

const ACCEPTED_MIME_TYPES: Record<string, string[]> = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
};

const MAX_JOB_DESC_CHARS = 10_000;

export function UploadForm({ onSubmit, isLoading, error }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [jobDescription, setJobDescription] = useState('');

  const onDrop = useCallback((acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
    setFileError(null);
    if (rejectedFiles.length > 0) {
      setFileError('Only PDF and DOCX files are accepted.');
      setFile(null);
      return;
    }
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_MIME_TYPES,
    maxFiles: 1,
    disabled: isLoading,
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!file) {
      setFileError('Please select a CV file.');
      return;
    }
    const formData = new FormData();
    formData.append('cv_file', file);
    if (jobDescription.trim()) {
      formData.append('job_description', jobDescription.trim());
    }
    onSubmit(formData);
  };

  const dropzoneClasses = [
    'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors',
    isDragActive
      ? 'border-blue-500 bg-blue-50'
      : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50',
    isLoading ? 'opacity-60 cursor-not-allowed' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6"
      aria-label="CV upload form"
    >
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Upload Your CV</h2>

      {/* Drop zone */}
      <div {...getRootProps()} className={dropzoneClasses} aria-label="File drop zone">
        <input {...getInputProps()} aria-label="CV file input" />
        <div className="flex flex-col items-center gap-2">
          {/* File icon */}
          <svg
            className="w-10 h-10 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>

          {file ? (
            <div className="text-sm">
              <span className="font-medium text-blue-600">{file.name}</span>
              <span className="text-gray-500 ml-2">
                ({(file.size / 1024).toFixed(0)} KB)
              </span>
            </div>
          ) : isDragActive ? (
            <p className="text-blue-600 font-medium">Drop your CV here</p>
          ) : (
            <div className="text-sm text-gray-600">
              <span className="font-medium text-blue-600 hover:underline">
                Drop your CV here or click to browse
              </span>
              <p className="text-gray-400 text-xs mt-1">PDF or DOCX · max 10 MB</p>
            </div>
          )}
        </div>
      </div>

      {/* File validation error */}
      {fileError && (
        <p className="mt-2 text-sm text-red-600" role="alert">
          {fileError}
        </p>
      )}

      {/* Job description */}
      <div className="mt-5">
        <label
          htmlFor="job-description"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          Job Description{' '}
          <span className="font-normal text-gray-400">(optional)</span>
        </label>
        <textarea
          id="job-description"
          rows={5}
          maxLength={MAX_JOB_DESC_CHARS}
          value={jobDescription}
          onChange={(e) => setJobDescription(e.target.value)}
          placeholder="Paste the job description here to get a job-fit adjusted score and salary estimate..."
          disabled={isLoading}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y disabled:opacity-60"
          aria-label="Job description"
        />
        <p className="text-xs text-gray-400 text-right mt-1">
          {jobDescription.length.toLocaleString()} / {MAX_JOB_DESC_CHARS.toLocaleString()}
        </p>
      </div>

      {/* Server error */}
      {error && (
        <div
          className="mt-4 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700"
          role="alert"
        >
          {error.message}
        </div>
      )}

      {/* Submit button */}
      <button
        type="submit"
        disabled={isLoading || !file}
        className="mt-5 w-full sm:w-auto bg-blue-600 text-white font-medium px-6 py-2.5 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        aria-label="Analyze CV"
      >
        {isLoading ? 'Analyzing…' : 'Analyze'}
      </button>
    </form>
  );
}
