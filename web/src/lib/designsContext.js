/* The context alone, with no renderer behind it: App.jsx supplies the value and must not pull cards/studio.js (the whole
   card renderer) into the first chunk just to create the context. Everything else imports it through ./designs.js. */
import { createContext, useContext } from "react";

export const DesignsContext = createContext({ designs: [], defaultId: "", ready: false, saveDesigns: null, setDefault: null });
export const useDesigns = () => useContext(DesignsContext);
