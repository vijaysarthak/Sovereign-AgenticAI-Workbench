import React from 'react';
import { useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

const AppLayout = ({ children }) => {
  const location = useLocation();
  const isWorkbench = location.pathname.includes('/workbench');

  return (
    <div className="min-h-screen bg-sov-bg flex w-full overflow-hidden text-sov-text-primary font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col ml-56 h-screen overflow-hidden">
        <TopBar />
        <main className={`flex-1 overflow-y-auto bg-sov-bg relative ${!isWorkbench ? 'p-6' : ''}`}>
          <div className={!isWorkbench ? 'max-w-7xl mx-auto h-full' : 'h-full'}>
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

export default AppLayout;
