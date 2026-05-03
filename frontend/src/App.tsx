import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import CaptionGenerator from './pages/CaptionGenerator';

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/caption" element={<CaptionGenerator />} />
      </Routes>
    </Router>
  );
};

export default App;
