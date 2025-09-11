import { PyodideService } from 'src/app/services/pyodide/pyodide.service';
import { Component, OnInit, ViewChild, ElementRef } from '@angular/core';
import { AbstractControl, FormControl, FormGroup, ReactiveFormsModule, ValidationErrors, ValidatorFn, Validators } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { HttpClientModule } from '@angular/common/http';

import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { faPython } from '@fortawesome/free-brands-svg-icons';


@Component({
  host: {'class': 'page-content'},
  selector: 'app-submit',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    CommonModule,
    ReactiveFormsModule,
    FontAwesomeModule,
    HttpClientModule
  ],
  templateUrl: './tabular.component.html',
  styleUrls: ['./tabular.component.css']
})
export class TabularComponent implements OnInit {
  protected form: any;
  protected logging_message: string = '';
  protected status: string = '';
  protected statusClass: string = "alert alert-info";
  protected disableSubmit: boolean = false;
  protected disableDownload: boolean = true;
  protected disableLog: boolean = true;
  protected loading: boolean = false;
  protected loadingStatus: string = "";
  protected progress: number = 0;
  protected file: File | null = null;
  @ViewChild('log_textarea1') myTextArea!: ElementRef;

  faPython = faPython;

  constructor(
    private pyodideService: PyodideService,
    private http: HttpClient
  ) { }

  ngOnInit() {
    this.form = new FormGroup({
      cluster_group_size: new FormControl(10, Validators.compose([Validators.required, Validators.pattern('[1-9][0-9]*')])),
      number_of_data: new FormControl(10, Validators.compose([Validators.required, Validators.pattern('[1-9][0-9]*')])),
      header_included: new FormControl(true),
      config_included: new FormControl(false),
      filePicker: new FormControl(''),
    }, []);
    this.disableSubmit = true;
    this.loading = true;
    this.pyodideService.load(
      (log_message)=>{this.loadingStatus = this.loadingStatus + log_message + "<br>"}
    ).then(() => {
      console.log("pyodideService loaded successfully.");
      this.pyodideService.registerOutput((z :string) => {

        let log_string = this.logging_message+z+"\n";
        let start_index = Math.max(0,log_string.length-1000);
        log_string = log_string.substr(start_index);
        if (start_index>0) log_string = ". . .\n"+log_string;
        this.logging_message=log_string;
        this.scrollToBottom();

        const match = z.match(/^Completed (\d+)\/(\d+)$/);
        if (match) {
          const integer1 = parseInt(match[1], 10);
          const integer2 = parseInt(match[2], 10);
          this.progress = integer1*100.0/integer2;
        }
      });
      this.loading = false;
      this.disableSubmit = false;
    })
    window.scrollTo(0, 0);
  }

  scrollToBottom(): void {
    if (this.myTextArea) {
      this.myTextArea.nativeElement.scrollTop = this.myTextArea.nativeElement.scrollHeight;
    }
  }


  // callback for file selection - need to store the File object
  handlePick(e: Event) {
    const files = (e.target as HTMLInputElement).files ?? new FileList();
    if (files.length == 0) { return; }
    if (files.length > 1) { alert('Cannot provide more than one file at a time.'); return; }
    const file: File = files.item(0)!;
    if (!file.name.toLowerCase().endsWith(".csv")) { alert('File extension did not match .csv'); return; }
    this.file = file;
  }

  // callback for download results button, load the FS object and simulate a download click
  async downloadResults() {
    try {
      const filename = "csv_output.csv";
      const blob = new Blob([this.pyodideService.readFile(filename)], { type: "application/octet-stream" });

      // Create download link and simulate click
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err) {
      this.logging_message = `Error: ${err}`;
    }
  }

  async submitJob() {
    if (!this.pyodideService.isLoaded()) {
      return;
    }
    if (this.file === null) {
      return;
    }
    this.progress = 0;
    this.disableSubmit = true;
    this.disableDownload = true;
    let cluster_group_size = this.form.value.cluster_group_size;
    let number_of_data = this.form.value.number_of_data;
    let header_included = this.form.value.header_included;
    let config_included = this.form.value.config_included;

    this.form.markAllAsTouched();
    this.form.markAsDirty();
    if (this.form.invalid) return;
    this.logging_message = "";
    this.disableLog = false;
    this.status = "Running";
    this.statusClass = "alert alert-info";
    this.pyodideService.loadFile(new Uint8Array(await this.file.arrayBuffer()), "csv_input.csv");
    this.pyodideService.execute(
      "Genomator_tabular_exec",["csv_input.csv","csv_output.csv",number_of_data,cluster_group_size,header_included,config_included]
    ).then (() => {
      this.progress = 100;
      this.status = "Finished";
      this.statusClass = "alert alert-success";

      this.disableSubmit = false;
      this.disableDownload = false;
    }, (error) => {
      this.progress = 0;
      this.status = "ERROR: "+error;
      this.statusClass = "alert alert-danger";
      this.disableSubmit = false;
    })
  }

  redirect(location:string) {
    document.location = location;
  }

  loadExample() {
    if (this.loading == false) {
      this.disableSubmit = true;
      this.disableDownload = true;
      this.http.get("assets/catdog.csv", { responseType: 'arraybuffer' }).subscribe(
        (data: ArrayBuffer) => {
          this.file = new File([data],"catdog.csv");
          this.form.patchValue({
            cluster_group_size: 10,
            number_of_data: 150,
            header_included: true,
            config_included: true
          })
          this.submitJob();
        }
      );
    }
  }
}
