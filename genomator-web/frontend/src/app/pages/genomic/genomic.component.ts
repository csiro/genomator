import { PyodideService } from 'src/app/services/pyodide/pyodide.service';
import {
  Component,
  OnInit,
  ViewChild,
  ElementRef,
  NgZone,
} from '@angular/core';
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
import { ToastrService } from 'ngx-toastr';

enum ParamMode {
  HighPrivacy = 'High Privacy',
  Balanced = 'Balanced',
  HighAccuracy = 'High Accuracy',
  Advanced = 'Advanced',
}

const mergeTwoSortedArrays = (arr1: any[], arr2: any[]) => {
  console.log('Merging two sorted arrays...');
  const merged: any[] = [];
  let i = 0;
  let j = 0;

  while (i < arr1.length && j < arr2.length) {
    if (parseInt(arr1[i][1], 10) < parseInt(arr2[j][1], 10)) {
      merged.push(arr1[i]);
      i++;
    } else {
      merged.push(arr2[j]);
      j++;
    }
  }

  // Append remaining elements
  while (i < arr1.length) {
    merged.push(arr1[i]);
    i++;
  }
  while (j < arr2.length) {
    merged.push(arr2[j]);
    j++;
  }

  console.log('Merging completed.');

  return merged;
};

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
  @ViewChild('log_textarea1') myTextArea!: ElementRef;
  @ViewChild('how_to_use') howToUseSection!: ElementRef;
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
  protected spikeFileContent: Array<Array<string>> | null = null;
  protected ParamMode = ParamMode;
  protected mode: ParamMode = ParamMode.Advanced;
  private startTime: number = 0;
  private endTime: number = 0;

  faPython = faPython;
  faGithub = faGithub;

  constructor(
    private pyodideService: PyodideService,
    private http: HttpClient,
    private ngZone: NgZone,
    private toastr: ToastrService,
  ) {}

  ngOnInit() {
    this.form = new FormGroup(
      {
        cluster_group_size: new FormControl(
          5,
          Validators.compose([
            Validators.required,
            Validators.pattern('[1-9][0-9]*'),
          ]),
        ),
        number_of_data: new FormControl(
          10,
          Validators.compose([
            Validators.required,
            Validators.pattern('[1-9][0-9]*'),
          ]),
        ),
        exception_space: new FormControl(
          0,
          Validators.compose([Validators.required]),
        ),
        looseness: new FormControl(
          0,
          Validators.compose([Validators.required]),
        ),
        filePicker: new FormControl(''),
        spikeFilePicker: new FormControl(''),
      },
      [],
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
          this.ngZone.run(() => {
            let log_string = this.logging_message + z + '\n';
            let start_index = Math.max(0, log_string.length - 1000);
            log_string = log_string.substr(start_index);
            if (start_index > 0) log_string = '. . .\n' + log_string;
            this.logging_message = log_string;
            this.scrollToBottom();
            this.setProgressString(z);
          });
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

  scrollTo(el: ElementRef<HTMLElement>) {
    el.nativeElement.scrollIntoView({ behavior: 'smooth' });
  }

  setMode(mode: ParamMode) {
    this.mode = mode;
    switch (mode) {
      case ParamMode.HighAccuracy:
        this.form.disable();
        this.form.patchValue({
          exception_space: 0,
          looseness: 0,
        });
        break;
      case ParamMode.Balanced:
        this.form.disable();
        this.form.patchValue({
          exception_space: 0.5,
          looseness: 0.5,
        });
        break;
      case ParamMode.HighPrivacy:
        this.form.disable();
        this.form.patchValue({
          exception_space: 1,
          looseness: 1,
        });
        break;
      case ParamMode.Advanced:
        this.form.enable();
        break;
    }
    this.form.get('cluster_group_size').enable();
    this.form.get('number_of_data').enable();
    this.form.get('filePicker').enable();
    this.form.get('spikeFilePicker').enable();
  }

  // callback for file selection - need to store the File object
  handlePick(e: Event) {
    const files = (e.target as HTMLInputElement).files ?? new FileList();
    if (files.length == 0) {
      return;
    }
    if (files.length > 1) {
      this.toastr.error(
        'Cannot provide more than one file at a time.',
        'Multiple Files Selected',
      );
      (e.target as HTMLInputElement).value = '';
      return;
    }
    const file: File = files.item(0)!;

    if (file.size > 1 * 1024 * 1024 * 1024) {
      this.toastr.error('File size exceeds 1GB limit.', 'File Too Large');
      return;
    }
    if (!file.name.toLowerCase().endsWith('.vcf')) {
      this.toastr.error(
        'File extension did not match .vcf',
        'Invalid File Extension',
      );
      (e.target as HTMLInputElement).value = '';
      return;
    }
    this.file = file;
  }

  handleSpikePick(e: Event) {
    const files = (e.target as HTMLInputElement).files ?? new FileList();
    if (files.length == 0) {
      return;
    }
    if (files.length > 1) {
      this.toastr.error(
        'Cannot provide more than one file at a time.',
        'Multiple Files Selected',
      );
      return;
    }
    const file: File = files.item(0)!;
    if (!file.name.toLowerCase().endsWith('.csv')) {
      this.toastr.error(
        'File extension did not match .csv',
        'Invalid File Extension',
      );
      return;
    }
    const reader = new FileReader();
    reader.onload = (event: any) => {
      const text = event.target.result;
      const lines = text.trim().split('\n');
      const rows: Array<Array<string>> = lines.map((line: string) =>
        line.trim().split(','),
      );

      if (rows.length === 0 || rows.length > 1000) {
        this.toastr.error(
          'Spike file must contain between 1 and 1000 variants.',
          'Invalid Spike File',
        );
        event.target.value = '';
        return;
      }

      this.spikeFileContent = rows.sort(
        (a, b) => parseInt(a[1], 10) - parseInt(b[1], 10),
      );
    };
    reader.readAsText(file);
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

  async downloadSpikedResults() {
    try {
      const filename = 'vcf_output.vcf';
      const dataArray = this.pyodideService.readFile(filename);
      const stringData = new TextDecoder().decode(dataArray);
      const vcfLines = stringData
        .split('\n')
        .map((line: string) => line.split('\t'));

      // For testing, use hardcoded VCF lines
      // const vcfLines = [
      //   '##vcf',
      //   '##fileformat=VCFv4.2',
      //   '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSMPL1',
      //   '1\t10177\trs367896724\tA\tAC\t100\tPASS\t.\t.\t0/1',
      //   '1\t10352\trs555500075\tT\tTA\t100\tPASS\t.\t.\t0/0',
      //   '1\t14389100\trs555500175\tG\tA\t100\tPASS\t.\t.\t0/1',
      //   '1\t14389500\ttrs555500275\tG\tA\t100\tPASS\t.\t.\t1/1',
      //   '2\t14389200\ttrs555500275\tG\tA\t100\tPASS\t.\t.\t1/1',
      // ].map((line) => line.split('\t'));

      if (!this.spikeFileContent) {
        this.toastr.error('No spike file loaded.', 'Missing Spike File');
        return;
      }
      const vcfHeader = vcfLines.filter((line) => line[0].startsWith('#'));
      const vcfDataLines = vcfLines.filter((line) => !line[0].startsWith('#'));
      const vcfDataRowLength = vcfDataLines[0].length;
      const vcfLinesByChrom: any = vcfDataLines.reduce(
        (acc: any, line: any) => {
          const chrom = line[0];
          if (!acc[chrom]) {
            acc[chrom] = [];
          }
          acc[chrom].push(line);
          return acc;
        },
        {},
      );

      const spikesByChrom = this.spikeFileContent.reduce(
        (acc: any, spike: any) => {
          if (!acc[spike[0]]) {
            acc[spike[0]] = [];
          }
          acc[spike[0]].push(spike);
          acc[spike[0]].sort((a: any, b: any) => a[1] - b[1]);
          return acc;
        },
        {},
      );

      for (const lines of Object.values(spikesByChrom)) {
        for (const line of lines as any[]) {
          if (line.length !== vcfDataRowLength) {
            this.toastr.error(
              `Spike file's line length ${line.length} does not match VCF data line length ${vcfDataRowLength}.`,
              'Invalid Spike File',
            );
            return;
          }
        }
      }

      console.log('Starting spiking process...');

      const spikedVcf = [...vcfHeader];

      for (const chrom in vcfLinesByChrom) {
        console.log(`Processing chromosome: ${chrom}`);

        if (!spikesByChrom[chrom]) {
          console.log(`No spikes for chromosome: ${chrom}`);
          spikedVcf.push(...vcfLinesByChrom[chrom]);
          continue;
        }

        const mergedLines = mergeTwoSortedArrays(
          vcfLinesByChrom[chrom],
          spikesByChrom[chrom],
        );

        for (const line of mergedLines) {
          spikedVcf.push(line);
        }

        console.log(`Finished chromosome: ${chrom}`);
      }

      console.log('Spiking process completed.');

      const blob = new Blob(
        [spikedVcf.map((line) => line.join('\t')).join('\n')],
        {
          type: 'text/plain',
        },
      );

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

  clearSpikeFile(e: Event) {
    e.preventDefault();
    this.spikeFileContent = null;
    this.form.patchValue({
      spikeFilePicker: '',
    });
  }

  // Prevent non-numeric keypresses to satisfy CSP (no inline handlers)
  allowNumberOnly(event: KeyboardEvent) {
    const allowed = ['Backspace', 'Tab', 'ArrowLeft', 'ArrowRight', 'Delete'];
    if (allowed.includes(event.key)) return;
    if (!/^[0-9]$/.test(event.key)) {
      event.preventDefault();
    }
  }

  async submitJob() {
    if (!this.pyodideService.isLoaded()) {
      return;
    }
    if (this.file === null) {
      return;
    }
    this.startTime = Date.now();
    this.setProgress(0);
    this.disableSubmit = true;
    this.disableDownload = true;
    const formValue = this.form.getRawValue();

    console.log('Form Value:', formValue);
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
      'vcf_input.vcf',
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
          this.endTime = Date.now();
          const timeTaken = (this.endTime - this.startTime) / 1000;
          this.logging_message += `\nTotal time taken: ${timeTaken.toFixed(
            2,
          )} seconds\n`;
        },
        (error) => {
          this.setProgress(0);
          if (error.message.includes('AssertionError:')) {
            this.status = 'ERROR: ' + error.message.split('AssertionError:')[1];
            this.toastr.error(this.status, 'Processing Error');
          } else {
            this.status = 'ERROR: ' + error;
          }
          this.statusClass = 'alert alert-danger';
          this.disableSubmit = false;

          console.log('msg', error.message);
          console.log('name', error.name);
        },
      );
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
          this.mode = ParamMode.Advanced;
          this.submitJob();
        });
    }
  }
}
