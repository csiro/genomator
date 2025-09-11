import { Injectable } from '@angular/core';
declare var loadPyodide: any;

type StringCallback = (message: string) => void;

@Injectable({
  providedIn: 'any'
})
export class PyodideService {
  public static pyodide:any;

  constructor() {
    PyodideService.pyodide = undefined;
  }

  async load(log_function: StringCallback) {
    try {
      if (PyodideService.pyodide === undefined) {
        // Load in Pyodide python interpreter, and required modules
        log_function("Loading in Pyodide...")
        PyodideService.pyodide = await loadPyodide();
        log_function("Loading in python-sat...")
        await PyodideService.pyodide.loadPackage("python-sat");
        log_function("Loading in numpy...")
        await PyodideService.pyodide.loadPackage("numpy");
        log_function("Loading in pysam...")
        await PyodideService.pyodide.loadPackage('pysam');
        log_function("Loading in click...")
        await PyodideService.pyodide.loadPackage('click');
        log_function("Loading in micropip...")
        await PyodideService.pyodide.loadPackage("micropip");
        const micropip = PyodideService.pyodide.pyimport("micropip");
        log_function("Loading in vcfpy...")
        await micropip.install('/assets/vcfpy-0.13.8-py2.py3-none-any.whl')

        // read and load-in python script
        log_function("setting up Python environment...")
        PyodideService.pyodide.runPython("__name__='loading_stuff'"); // prevent __name__=="__main__" execution
        log_function("Loading in Genomator for genome data...")
        PyodideService.pyodide.runPython(await (await fetch('assets/genomator_mini')).text());
        log_function("Loading in Genomator for tabular data...")
        PyodideService.pyodide.runPython(await (await fetch('assets/genomator_mini_tabular')).text());
        PyodideService.pyodide.runPython("silent=False"); // verbose
        log_function("Pyodide loaded.")
      } else {
        log_function("Pyodide already loaded.")
      }
    } catch (error) {
      log_function("LOADING FAILED! (try refreshing browser page): " + error)
      throw error;
    }
  }

  isLoaded() : boolean {
    return PyodideService.pyodide !== undefined;
  }

  loadFile(file_contents: Uint8Array, filename: string) {
    PyodideService.pyodide.FS.writeFile(filename, file_contents);
  }

  async execute(f: string, args: (string | number)[]) {
    await PyodideService.pyodide.globals.get(f).call(null, ...args);
  }

  readFile(file: string) : Uint8Array {
    return PyodideService.pyodide.FS.readFile(file);
  }

  registerOutput(func: any) : void {
    PyodideService.pyodide.setStdout({ batched: func });
  }
}
