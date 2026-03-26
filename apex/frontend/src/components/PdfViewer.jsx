import { X, Download } from 'lucide-react';

export default function PdfViewer({ url, filename, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-900 text-white">
        <span className="font-medium truncate">{filename}</span>
        <div className="flex items-center gap-2">
          <a href={url} download={filename} className="p-2 hover:bg-gray-700 rounded" title="Download">
            <Download size={18} />
          </a>
          <button onClick={onClose} className="p-2 hover:bg-gray-700 rounded" title="Close">
            <X size={18} />
          </button>
        </div>
      </div>
      {/* PDF content */}
      <div className="flex-1 overflow-hidden">
        <iframe
          src={url}
          className="w-full h-full border-0"
          title={filename}
        />
      </div>
    </div>
  );
}
