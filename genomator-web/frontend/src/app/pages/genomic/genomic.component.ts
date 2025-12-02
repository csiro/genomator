import { PyodideService } from 'src/app/services/pyodide/pyodide.service';
import { Component, OnInit, ViewChild, ElementRef } from '@angular/core';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { HttpClientModule } from '@angular/common/http';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { faPython } from '@fortawesome/free-brands-svg-icons';
import { faGithub } from '@fortawesome/free-brands-svg-icons';

enum ParamMode {
  HighPrivacy = 'High Privacy',
  Balanced = 'Balanced',
  HighAccuracy = 'High Accuracy',
  Advanced = 'Advanced',
}

@Component({
  host: { class: 'page-content' },
  selector: 'app-submit',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    CommonModule,
    ReactiveFormsModule,
    FontAwesomeModule,
    HttpClientModule,
  ],
  templateUrl: './genomic.component.html',
  styleUrls: ['./genomic.component.css'],
})
export class GenomicComponent implements OnInit {
  protected form: any;
  protected logging_message: string = '';
  protected status: string = '';
  protected statusClass: string = 'alert alert-info';
  protected disableSubmit: boolean = false;
  protected disableDownload: boolean = true;
  protected disableLog: boolean = true;
  protected loading: boolean = false;
  protected loadingStatus: string = '';
  protected progress1: number = 0;
  protected progress2: number = 0;
  protected progress3: number = 0;
  protected progress4: number = 0;
  protected progress5: number = 0;
  protected file: File | null = null;
  protected ParamMode = ParamMode;
  protected mode: ParamMode = ParamMode.Advanced;
  @ViewChild('log_textarea1') myTextArea!: ElementRef;

  faPython = faPython;
  faGithub = faGithub;

  constructor(
    private pyodideService: PyodideService,
    private http: HttpClient
  ) {}

  ngOnInit() {
    this.form = new FormGroup(
      {
        cluster_group_size: new FormControl(
          10,
          Validators.compose([
            Validators.required,
            Validators.pattern('[1-9][0-9]*'),
          ])
        ),
        number_of_data: new FormControl(
          10,
          Validators.compose([
            Validators.required,
            Validators.pattern('[1-9][0-9]*'),
          ])
        ),
        exception_space: new FormControl(
          0,
          Validators.compose([Validators.required])
        ),
        looseness: new FormControl(
          0,
          Validators.compose([Validators.required])
        ),
        filePicker: new FormControl(''),
      },
      []
    );
    this.disableSubmit = true;
    this.loading = true;
    this.pyodideService
      .load((log_message) => {
        this.loadingStatus = this.loadingStatus + log_message + '<br>';
      })
      .then(() => {
        console.log('pyodideService loaded successfully.');
        this.pyodideService.registerOutput((z: string) => {
          let log_string = this.logging_message + z + '\n';
          let start_index = Math.max(0, log_string.length - 1000);
          log_string = log_string.substr(start_index);
          if (start_index > 0) log_string = '. . .\n' + log_string;
          this.logging_message = log_string;
          this.scrollToBottom();
          this.setProgressString(z);
        });
        this.loading = false;
        this.disableSubmit = false;
      });
    window.scrollTo(0, 0);
    this.setMode(ParamMode.Balanced);
  }

  scrollToBottom(): void {
    if (this.myTextArea) {
      this.myTextArea.nativeElement.scrollTop =
        this.myTextArea.nativeElement.scrollHeight;
    }
  }

  setMode(mode: ParamMode) {
    this.mode = mode;
    switch (mode) {
      case ParamMode.HighAccuracy:
        this.form.disable();
        this.form.patchValue({
          cluster_group_size: 5,
          exception_space: 0,
          looseness: 0,
        });
        break;
      case ParamMode.Balanced:
        this.form.disable();
        this.form.patchValue({
          cluster_group_size: 75,
          exception_space: 0.5,
          looseness: 0.5,
        });
        break;
      case ParamMode.HighPrivacy:
        this.form.disable();
        this.form.patchValue({
          cluster_group_size: 150,
          exception_space: 1,
          looseness: 1,
        });
        break;
      case ParamMode.Advanced:
        this.form.enable();
        break;
    }
    this.form.get('number_of_data').enable();
    this.form.get('filePicker').enable();
  }

  // callback for file selection - need to store the File object
  handlePick(e: Event) {
    const files = (e.target as HTMLInputElement).files ?? new FileList();
    if (files.length == 0) {
      return;
    }
    if (files.length > 1) {
      alert('Cannot provide more than one file at a time.');
      return;
    }
    const file: File = files.item(0)!;
    if (!file.name.toLowerCase().endsWith('.vcf')) {
      alert('File extension did not match .vcf');
      return;
    }
    this.file = file;
  }

  setProgressString(s: string) {
    let match: any = false;
    if (s.startsWith('loaded variants ')) {
      match = s.match(/^loaded variants (\d+)\/(\d+)$/);
      if (match)
        this.progress1 =
          (parseInt(match[1], 10) * 100.0) / parseInt(match[2], 10);
    }
    if (s.startsWith('cluster distance iteration ')) {
      match = s.match(/^cluster distance iteration (\d+)\/(\d+)$/);
      if (match)
        this.progress2 =
          (parseInt(match[1], 10) * 100.0) / parseInt(match[2], 10);
    }
    if (s.startsWith('cluster re run ')) {
      match = s.match(/^cluster re run (\d+)\/(\d+)$/);
      if (match)
        this.progress3 =
          (parseInt(match[1], 10) * 100.0) / parseInt(match[2], 10);
    }
    if (s.startsWith('Completed ')) {
      match = s.match(/^Completed (\d+)\/(\d+)$/);
      if (match)
        this.progress4 =
          (parseInt(match[1], 10) * 100.0) / parseInt(match[2], 10);
    }
    if (s.startsWith('output records ')) {
      match = s.match(/^output records (\d+)\/(\d+)$/);
      if (match)
        this.progress5 =
          (parseInt(match[1], 10) * 100.0) / parseInt(match[2], 10);
    }
  }
  setProgress(i: number) {
    this.progress1 = i;
    this.progress2 = i;
    this.progress3 = i;
    this.progress4 = i;
    this.progress5 = i;
  }

  // callback for download results button, load the FS object and simulate a download click
  async downloadResults() {
    try {
      const filename = 'vcf_output.vcf';
      const blob = new Blob([this.pyodideService.readFile(filename) as any], {
        type: 'application/octet-stream',
      });

      // Create download link and simulate click
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err) {
      this.logging_message = `Error: ${err}`;
      this.scrollToBottom();
    }
  }

  async submitJob() {
    if (!this.pyodideService.isLoaded()) {
      return;
    }
    if (this.file === null) {
      return;
    }
    this.setProgress(0);
    this.disableSubmit = true;
    this.disableDownload = true;
    const formValue = this.form.getRawValue();
    let cluster_group_size = formValue.cluster_group_size;
    let number_of_data = formValue.number_of_data;
    let exception_space = formValue.exception_space;
    let looseness = formValue.looseness;
    this.form.markAllAsTouched();
    this.form.markAsDirty();
    if (this.form.invalid) return;
    this.logging_message = '';
    this.disableLog = false;
    this.status = 'Running';
    this.statusClass = 'alert alert-info';
    this.pyodideService.loadFile(
      new Uint8Array(await this.file.arrayBuffer()),
      'vcf_input.vcf'
    );
    this.pyodideService
      .execute('Genomator_exec', [
        'vcf_input.vcf',
        'vcf_output.vcf',
        number_of_data,
        -exception_space,
        cluster_group_size,
        looseness,
      ])
      .then(
        () => {
          this.setProgress(100);
          this.status = 'Finished';
          this.statusClass = 'alert alert-success';

          this.disableSubmit = false;
          this.disableDownload = false;
        },
        (error) => {
          this.setProgress(0);
          this.status = 'ERROR: ' + error;
          this.statusClass = 'alert alert-danger';
          this.disableSubmit = false;
        }
      );
  }

  redirect(location: string) {
    document.location = location;
  }

  loadExample() {
    if (this.loading == false) {
      this.disableSubmit = true;
      this.disableDownload = true;
      this.http
        .get('assets/805_SNP_1000G_real.vcf', { responseType: 'arraybuffer' })
        .subscribe((data: ArrayBuffer) => {
          this.file = new File([data], '805_SNP_1000G_real.vcf');
          this.form.patchValue({
            cluster_group_size: 10,
            number_of_data: 1000,
            exception_space: 0,
            looseness: 0,
          });
          this.submitJob();
        });
    }
  }
}
