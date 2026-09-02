import { PyodideService } from 'src/app/services/pyodide/pyodide.service';
import { Component, NgZone, OnInit } from '@angular/core';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ToastrService } from 'ngx-toastr';

enum CalculateMode {
  Accuracy = 'Accuracy',
  Privacy = 'Privacy',
  InDepth = 'InDepth',
}

enum GenParamMode {
  HighPrivacy = 'High Privacy',
  Balanced = 'Balanced',
  HighAccuracy = 'High Accuracy',
  Advanced = 'Advanced',
}

@Component({
  host: { class: 'page-content' },
  selector: 'app-calculate-privacy-metric',
  standalone: true,
  imports: [ReactiveFormsModule, CommonModule, RouterLink],
  templateUrl: './calculate-privacy-metric.component.html',
  styleUrls: ['./calculate-privacy-metric.component.css'],
})
export class CalculatePrivacyMetricComponent implements OnInit {
  protected CalculateMode = CalculateMode;
  protected mode: CalculateMode = CalculateMode.Accuracy;
  protected GenParamMode = GenParamMode;
  protected genMode: GenParamMode = GenParamMode.Balanced;

  protected form: any;
  protected inputFile: File | null = null;
  protected generatedFile: File | null = null;

  protected loading: boolean = false;
  protected loadingStatus: string = '';
  protected disableSubmit: boolean = false;
  protected disableLog: boolean = true;
  protected logging_message: string = '';
  protected status: string = '';
  protected statusClass: string = 'alert alert-info';
  protected progress: number = 0;
  protected result: string | null = null;

  constructor(
    private pyodideService: PyodideService,
    private ngZone: NgZone,
    private toastr: ToastrService,
  ) {}

  ngOnInit(): void {
    this.form = new FormGroup({
      inputFilePicker: new FormControl(''),
      generatedFilePicker: new FormControl(''),
      accuracyTrials: new FormControl(
        50,
        Validators.compose([
          Validators.required,
          Validators.pattern('[1-9][0-9]*'),
        ]),
      ),
      slices: new FormControl(
        300,
        Validators.compose([
          Validators.required,
          Validators.pattern('[1-9][0-9]*'),
        ]),
      ),
      privacyTrials: new FormControl(
        100000,
        Validators.compose([
          Validators.required,
          Validators.pattern('[1-9][0-9]*'),
        ]),
      ),
      degree: new FormControl(
        4,
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
      cluster_group_size: new FormControl(
        5,
        Validators.compose([
          Validators.required,
          Validators.pattern('[1-9][0-9]*'),
        ]),
      ),
      exception_space: new FormControl(
        0.5,
        Validators.compose([Validators.required]),
      ),
      looseness: new FormControl(
        0.5,
        Validators.compose([Validators.required]),
      ),
      auto_looseness: new FormControl(true),
    });

    this.disableSubmit = true;
    this.loading = true;
    this.pyodideService
      .load((log_message) => {
        this.loadingStatus = this.loadingStatus + log_message + '<br>';
      })
      .then(() => {
        this.pyodideService.registerOutput((z: string) => {
          this.ngZone.run(() => {
            let log_string = this.logging_message + z + '\n';
            const start_index = Math.max(0, log_string.length - 1000);
            log_string = log_string.substr(start_index);
            if (start_index > 0) log_string = '. . .\n' + log_string;
            this.logging_message = log_string;
            this.setProgressString(z);
          });
        });
        this.loading = false;
        this.disableSubmit = false;
      });
    this.setGenMode(GenParamMode.Balanced);
  }

  setMode(mode: CalculateMode) {
    this.mode = mode;
  }

  setGenMode(mode: GenParamMode) {
    this.genMode = mode;
    const lockedControls = ['cluster_group_size', 'exception_space', 'looseness'];
    switch (mode) {
      case GenParamMode.HighAccuracy:
        lockedControls.forEach((c) => this.form.get(c)?.disable());
        this.form.patchValue({
          cluster_group_size: 5,
          exception_space: 0,
          looseness: 0,
          auto_looseness: true,
        });
        break;
      case GenParamMode.Balanced:
        lockedControls.forEach((c) => this.form.get(c)?.disable());
        this.form.patchValue({
          cluster_group_size: 5,
          exception_space: 0.5,
          looseness: 0.5,
          auto_looseness: true,
        });
        break;
      case GenParamMode.HighPrivacy:
        lockedControls.forEach((c) => this.form.get(c)?.disable());
        this.form.patchValue({
          cluster_group_size: 10,
          exception_space: 1,
          looseness: 0.99,
          auto_looseness: true,
        });
        break;
      case GenParamMode.Advanced:
        lockedControls.forEach((c) => this.form.get(c)?.enable());
        this.form.patchValue({
          auto_looseness: false,
        });
        break;
    }
  }

  // Prevent non-numeric keypresses to satisfy CSP (no inline handlers)
  allowNumberOnly(event: KeyboardEvent) {
    const allowed = ['Backspace', 'Tab', 'ArrowLeft', 'ArrowRight', 'Delete'];
    if (allowed.includes(event.key)) return;
    if (!/^[0-9]$/.test(event.key)) {
      event.preventDefault();
    }
  }

  private validateAndPickVcf(e: Event): File | null {
    const files = (e.target as HTMLInputElement).files ?? new FileList();
    if (files.length == 0) {
      return null;
    }
    if (files.length > 1) {
      this.toastr.error(
        'Cannot provide more than one file at a time.',
        'Multiple Files Selected',
      );
      (e.target as HTMLInputElement).value = '';
      return null;
    }
    const file: File = files.item(0)!;
    if (file.size > 1 * 1024 * 1024 * 1024) {
      this.toastr.error('File size exceeds 1GB limit.', 'File Too Large');
      (e.target as HTMLInputElement).value = '';
      return null;
    }
    if (!file.name.toLowerCase().endsWith('.vcf')) {
      this.toastr.error(
        'File extension did not match .vcf',
        'Invalid File Extension',
      );
      (e.target as HTMLInputElement).value = '';
      return null;
    }
    return file;
  }

  handleInputPick(e: Event) {
    const file = this.validateAndPickVcf(e);
    if (file) this.inputFile = file;
  }

  handleGeneratedPick(e: Event) {
    const file = this.validateAndPickVcf(e);
    if (file) this.generatedFile = file;
  }

  setProgressString(s: string) {
    const trialMatch = s.match(/^(?:accuracy|privacy) trial (\d+)\/(\d+)$/);
    if (trialMatch) {
      this.progress =
        (parseInt(trialMatch[1], 10) * 100.0) / parseInt(trialMatch[2], 10);
      return;
    }
    const stageMatch = s.match(/^indepth stage (\d+)\/(\d+)/);
    if (stageMatch) {
      this.progress =
        (parseInt(stageMatch[1], 10) * 100.0) / parseInt(stageMatch[2], 10);
    }
  }

  async runMetric() {
    if (this.mode === CalculateMode.Accuracy) {
      await this.runTwoFileMetric('Accuracy_metric_exec', 'accuracyTrials', 'slices');
    } else if (this.mode === CalculateMode.Privacy) {
      await this.runTwoFileMetric('Privacy_metric_exec', 'privacyTrials', 'degree');
    } else {
      await this.runInDepthMetric();
    }
  }

  // shared status/progress/error bookkeeping around a metric execution
  private async withStatusHandling(action: () => Promise<any>) {
    this.progress = 0;
    this.result = null;
    this.disableSubmit = true;
    this.logging_message = '';
    this.disableLog = false;
    this.status = 'Running';
    this.statusClass = 'alert alert-info';

    try {
      const result = await action();
      this.result = String(result);
      this.progress = 100;
      this.status = 'Finished';
      this.statusClass = 'alert alert-success';
    } catch (error: any) {
      this.progress = 0;
      if (error?.message?.includes('AssertionError:')) {
        this.status = 'ERROR: ' + error.message.split('AssertionError:')[1];
        this.toastr.error(this.status, 'Processing Error');
      } else {
        this.status = 'ERROR: ' + error;
      }
      this.statusClass = 'alert alert-danger';
    } finally {
      this.disableSubmit = false;
    }
  }

  private async runTwoFileMetric(
    pythonFunction: string,
    trialsControl: string,
    secondParamControl: string,
  ) {
    if (!this.pyodideService.isLoaded()) {
      return;
    }
    if (this.inputFile === null || this.generatedFile === null) {
      this.toastr.error(
        'Please select both the input and generated VCF files.',
        'Missing Files',
      );
      return;
    }
    this.form.markAllAsTouched();
    if (this.form.invalid) return;

    const formValue = this.form.getRawValue();
    const inputFile = this.inputFile;
    const generatedFile = this.generatedFile;
    await this.withStatusHandling(async () => {
      this.pyodideService.loadFile(
        new Uint8Array(await inputFile.arrayBuffer()),
        'metric_input.vcf',
      );
      this.pyodideService.loadFile(
        new Uint8Array(await generatedFile.arrayBuffer()),
        'metric_generated.vcf',
      );
      return this.pyodideService.execute(pythonFunction, [
        'metric_input.vcf',
        'metric_generated.vcf',
        formValue[trialsControl],
        formValue[secondParamControl],
      ]);
    });
  }

  private async runInDepthMetric() {
    if (!this.pyodideService.isLoaded()) {
      return;
    }
    if (this.inputFile === null) {
      this.toastr.error(
        'Please select the input VCF file.',
        'Missing File',
      );
      return;
    }
    this.form.markAllAsTouched();
    if (this.form.invalid) return;

    const formValue = this.form.getRawValue();
    const inputFile = this.inputFile;
    await this.withStatusHandling(async () => {
      this.pyodideService.loadFile(
        new Uint8Array(await inputFile.arrayBuffer()),
        'indepth_cohort_input.vcf',
      );
      return this.pyodideService.execute('InDepth_privacy_metric_exec', [
        'indepth_cohort_input.vcf',
        formValue.number_of_data,
        formValue.exception_space,
        formValue.cluster_group_size,
        formValue.auto_looseness ? null : formValue.looseness,
      ]);
    });
  }
}
