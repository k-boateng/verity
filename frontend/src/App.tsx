import { Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Reader from "./pages/Reader";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/read/:docId" element={<Reader />} />
    </Routes>
  );
}
