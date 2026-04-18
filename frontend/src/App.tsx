import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import CaptionGenerator from './pages/CaptionGenerator';
import MultiAgentDiscussion from './pages/MultiAgentDiscussion';
import DeepResearch from './pages/DeepResearch';

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/caption" element={<CaptionGenerator />} />
        <Route path="/multi-agent" element={<MultiAgentDiscussion />} />
        <Route path="/deep-research" element={<DeepResearch />} />
      </Routes>
    </Router>
  );
};

export default App;
