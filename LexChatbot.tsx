'use client';

import { useEffect } from 'react';

interface ChatBotUiLoader {
  IframeLoader: new (opts: any) => {
    load: (config: any) => Promise<any>;
  };
}

declare global {
  interface Window {
    ChatBotUiLoader?: ChatBotUiLoader;
  }
}

export default function LexChatbot() {
  useEffect(() => {
    // Create and append the script tag
    const script = document.createElement('script');
    script.src = 'https://cloudfront-snippet...';
    script.async = true;
    
    // Initialize the chatbot when the script loads
    script.onload = () => {
      if (window.ChatBotUiLoader) {
        const loaderOpts = {
          baseUrl: 'https://cloudfront-snippet...',
          shouldLoadMinDeps: true
        };
        
        const loader = new window.ChatBotUiLoader.IframeLoader(loaderOpts);
        const chatbotUiConfig = {
          /* Example of setting session attributes on parent page
          lex: {
            sessionAttributes: {
              userAgent: navigator.userAgent,
              QNAClientFilter: ''
            }
          }
          */
        };
        
        loader.load(chatbotUiConfig)
          .catch((error: Error) => console.error(error));
      }
    };
    
    // Append the script to the document
    document.body.appendChild(script);
    
    // Clean up function
    return () => {
      if (script.parentNode) {
        script.parentNode.removeChild(script);
      }
    };
  }, []);
  
  return null; // This component doesn't render anything visible
}
