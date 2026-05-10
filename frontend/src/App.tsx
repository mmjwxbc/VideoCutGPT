import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import CaptionGenerator from './pages/CaptionGenerator';
import { ThemeProvider } from './theme/ThemeProvider';

const App: React.FC = () => {
  return (
    <ThemeProvider>
      <Router>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/caption" element={<CaptionGenerator />} />
        </Routes>
      </Router>
    </ThemeProvider>
  );
};

export default App;
