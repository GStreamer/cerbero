# SPDX-FileCopyrightText: 2024 L. E. Segovia <amy@centricular.com>
# SPDX-License-Ref: LGPL-2.1-or-later

from pathlib import Path
import shlex
import shutil
import tempfile
from zipfile import ZipFile

from cerbero.config import Platform
from cerbero.errors import EmptyPackageError
from cerbero.packages import PackagerBase, PackageType
from cerbero.packages.package import Package, App
from cerbero.packages.ninja_syntax import Writer
from cerbero.packages.wix import Fragment, MergeModule, MSI, VSMergeModule, VSTemplatePackage, WixConfig
from cerbero.utils import get_wix_prefix, m, shell


class Candle(object):
    """Compile WiX objects with candle"""

    options = {}

    def compile(self, writer: Writer, inputs: list[str], output: str, implicit_outputs=None, implicit_deps=None):
        """
        Write the rules to compile $inputs into $output_dir/$outputs
        """
        writer.build(
            output,
            'candle',
            inputs,
            implicit_outputs=implicit_outputs,
            implicit=implicit_deps,
            # Fixes error CNDL0050 : Access to the path '(...)\gstreamer-1.0-net-restricted.wxs.d' is denied.
            variables={'outdir': f'{Path(output).parent.as_posix()}/'},
        )
        writer.newline()

    def rule(writer: Writer, wix_prefix: str, with_wine: bool) -> None:
        """
        The template rule for compiling Wix objects
        """
        command = [f'{Path(__file__).parent}/wrapper.py', 'wine'] if with_wine else []
        outdir = 'posix:$outdir' if with_wine else '$outdir'
        inflag = '--' if with_wine else ''
        command.extend([(Path(wix_prefix) / 'candle.exe').as_posix(), '-nologo', '-out', outdir, '-wx', inflag, '$in'])

        writer.rule(
            'candle',
            ' '.join(command),
            description='Compiling WiX module $out',
        )
        writer.newline()


class Light(object):
    """Link WiX objects with light"""

    options = {}

    def __init__(self, extra=[]):
        self.options['extra'] = extra

    def compile(self, writer: Writer, objects: list[str], msi_name: str, merge_module=False, implicit_deps=None):
        """
        Write the rules to link WiX objects together into a MSM/MSI
        """
        if not objects:
            raise RuntimeError('Objects cannot be empty')
        wix_bin_name = f"{msi_name}.{'msm' if merge_module else 'msi'}"
        writer.build(
            wix_bin_name,
            'light',
            objects,
            implicit=implicit_deps,
            variables={'extra': self.options['extra']},
        )
        writer.newline()
        return wix_bin_name

    def rule(writer: Writer, wix_prefix: str, with_wine: bool) -> None:
        """
        The template rule for linking Wix objects into Merge Modules or MSI installers
        """
        command = [f'{Path(__file__).parent}/wrapper.py', 'wine'] if with_wine else []
        outobj = 'posix:$out' if with_wine else '$out'
        inflag = '--' if with_wine else ''
        # FIXME: remove -sval once the string overflows in component/file keys are solved
        command.extend(
            [(Path(wix_prefix) / 'light.exe').as_posix(), '-nologo', '-out', outobj, '$extra', '-sval', inflag, '$in']
        )

        if with_wine:
            command.extend(['&&', 'chmod', '0755', '$out'])

        writer.rule(
            'light',
            ' '.join(command),
            description='Linking $out',
        )


class StripRule(object):
    """Wrapper for the strip tool"""

    def __init__(self, config, keep_symbols=None):
        self.config = config
        self.keep_symbols = keep_symbols or []

    def rule(writer: Writer, config):
        if 'STRIP' not in config.env:
            m.warning('Strip command is not defined for this configuration, skipping rule generation')
            return

        strip_cmd = shlex.split(config.env['STRIP'])

        # This is NOT windows -- don't waste checks
        strip_cmd.extend(
            [
                '-o',
                '$out',
                '$extra',  # -K goes here
                '--strip-unneeded',
                '$in',
            ]
        )

        if config.target_platform == Platform.DARWIN:
            strip_cmd.append('-x')

        writer.rule('strip', ' '.join(strip_cmd), description='Stripping $out')
        writer.newline()

        copy_cmd = [
            Path(config.python).as_posix(),
            '-c',
            '"from sys import argv; from shutil import copy; copy(argv[1], argv[2])"',
            '$in',
            '$out',
        ]

        writer.rule('copy', ' '.join(copy_cmd), description='Copying $out')
        writer.newline()

    def copy_file(self, writer: Writer, source_dir: Path, input_filename: Path, output_dir: Path):
        writer.build(
            Path(output_dir / input_filename).as_posix(),
            'copy',
            Path(source_dir / input_filename).as_posix(),
        )
        writer.newline()

    def strip_file(self, writer: Writer, source_dir: Path, input_filename: Path, output_dir: Path):
        if 'STRIP' not in self.config.env:
            m.warning('Strip command is not defined for this configuration')
            return

        extra = []

        for symbol in self.keep_symbols:
            extra += ['-K', symbol]

        writer.build(
            Path(output_dir / input_filename).as_posix(),
            'strip',
            Path(source_dir / input_filename).as_posix(),
            variables={'extra': extra},
        )
        writer.newline()

    def strip_dir(self, writer: Writer, source_root, output_root):
        srcd = Path(source_root)
        outd = Path(output_root)
        for dirpath, _, filenames in srcd.walk(follow_symlinks=True):
            for f in filenames:
                # Send path relative to dir_path
                self.strip_file(writer, source_root, Path(dirpath) / f, outd)


class MergeModuleWithNinjaPackager(PackagerBase):
    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self._with_wine = config.platform != Platform.WINDOWS
        self.wix_prefix = get_wix_prefix(config)

    def is_strippable_file(filename: Path, package: Package):
        return any([filename.parent().is_relative_to(x) for x in package.strip_dirs]) and not any(
            [filename.name in path for path in package.strip_excludes]
        )

    def strip_files(self, writer: Writer, package_type, force=False):
        """
        Prepare the temporary roots for stripped files
        """
        tmpdir = None
        if self.package.strip and 'STRIP' in self.config.env:
            tmpdir = Path(f'{self.package.name}.stripped.d')
            prefix = Path(self.config.prefix)
            s = StripRule(self.config)
            # Now we need to filter the list in two parts:
            outputs = []

            for file in self.files_list(package_type, force):
                filename = Path(file)
                dst: Path = tmpdir / filename

                if self.is_strippable_file(filename, self.package):
                    # Those with parent in strip_dirs, insert stripping rules
                    s.strip_file(writer, prefix, filename, tmpdir)
                else:
                    # Those without, mkdir and copy
                    s.copy_file(writer, prefix, filename, tmpdir)
                outputs.append(dst)
            tmpdir = tmpdir
            writer.build(
                tmpdir,
                'phony',
                outputs,
            )
        return tmpdir

    def pack(self, output_dir, devel=False, force=False, keep_temp=False):
        """
        Create the scroll of incantation and then call Ninja to assemble it
        """

        PackagerBase.pack(self, output_dir, devel, force, keep_temp)
        # Let's make a temporary directory, that can be cleaned up in one go
        # This is the directory where Ninja will run
        output_dir = Path(output_dir).absolute()
        self.output_dir = Path(tempfile.mkdtemp(prefix=f'merge-module-{self._package_name()}-'))
        # These are the outputs of the Ninja process
        # All the paths must be understood relative to self.output_dir
        paths: list[Path] = []

        # For packages that requires stripping object files, we need
        # to copy all the files to a new tree and strip them there:
        package_types = [PackageType.RUNTIME]
        if devel:
            package_types.append(PackageType.DEVEL)

        # Set Ninja build file up
        m.action('Creating Ninja project for Merge Module')
        with (self.output_dir / 'build.ninja').open('w', encoding='utf-8') as rules:
            writer = Writer(rules, width=120)

            writer.comment(f'This is the build file for the merge module "{self._package_name()}"')
            writer.comment('It is autogenerated by Cerbero.')
            writer.comment('Do not edit by hand.')
            writer.newline()
            writer._line('ninja_required_version = 1.1')
            writer.newline()
            writer.newline()

            # Set Candle and Light rules up
            writer.comment('Incantations for the WiX Toolkit')
            writer.newline()
            Candle.rule(writer, self.wix_prefix, self._with_wine)
            Light.rule(writer, self.wix_prefix, self._with_wine)
            StripRule.rule(writer, self.config)
            writer.newline()

            writer.comment('Incantations for stripping files')
            writer.newline()
            tmpdirs = {t: self.strip_files(t, force) for t in package_types}
            writer.newline()

            # set rules for runtime package
            writer.comment('Incantations for the runtime package generation')
            writer.newline()
            p = self.create_merge_module(
                writer,
                PackageType.RUNTIME,
                force,
                self.package.version,
                stripped_dir=tmpdirs.get(PackageType.RUNTIME, None),
            )
            if p:
                paths.append(p)
                writer.newline()

            # set rules for devel package
            if devel:
                writer.comment('Incantations for the development package generation')
                writer.newline()
                p = self.create_merge_module(
                    writer,
                    PackageType.DEVEL,
                    force,
                    self.package.version,
                    stripped_dir=tmpdirs.get(PackageType.RUNTIME, None),
                )
                if p:
                    paths.append(p)
                    writer.newline()

            writer.close()

        # Execute ninja on the chosen output directory
        m.action('Building Merge Module in {self.output_dir}')

        # Ensure all the WiX temporary files are reaped at the end of execution
        with tempfile.TemporaryDirectory(prefix='wix-') as tmp:
            env = self.config.env.copy()
            env['TMP'] = tmp
            shell.new_call(['ninja'], cmd_dir=self.output_dir, env=env)

        # Copy the outputs to the output directory
        for p in paths:
            src = self.output_dir / p
            dst = output_dir / p
            m.action(f'Moving {p} to {output_dir}')
            shutil.move(src, dst)

        # Clean up
        # We need to tally up the temporaries now
        if keep_temp:
            m.action(f'Temporary build directory is at {self.output_dir}')
        else:
            shutil.rmtree(self.output_dir)

        return paths

    def create_merge_module(self, writer: Writer, package_type: PackageType, force: bool, version, stripped_dir=None):
        self.package.set_mode(package_type)
        try:
            files_list: list[str] = self.files_list(package_type, force)
        except EmptyPackageError:
            m.warning('Package %s is empty, skipping module generation' % self.package.name)
            return None
        if isinstance(self.package, VSTemplatePackage):
            mergemodule = VSMergeModule(self.config, files_list, self.package)
        else:
            mergemodule = MergeModule(self.config, files_list, self.package)

        package_name = self.package.name

        implicit_wixobjs = []
        if self.package.wix_use_fragment:
            mergemodule = Fragment(self.config, files_list, self.package)
            sources = [f'{package_name}-fragment.wxs']
            wixobj = f'{package_name}-fragment.wxs.d/{package_name}-fragment.wixobj'
        else:
            mergemodule = MergeModule(self.config, files_list, self.package)
            sources = [f'{package_name}.wxs']
            wixobj = f'{package_name}.wxs.d/{package_name}.wixobj'

        sources.append((Path(self.config.data_dir).absolute() / 'wix' / 'utils.wxs').as_posix())
        if self.package.wix_use_fragment:
            implicit_wixobjs = [f'{package_name}-fragment.wxs.d/utils.wixobj']
        else:
            implicit_wixobjs = [f'{package_name}.wxs.d/utils.wixobj']

        # There's a ready-made stripped folder here
        implicit_deps = None
        if stripped_dir:
            implicit_deps = [stripped_dir]
            mergemodule.prefix = Path(self.output_dir / stripped_dir).as_posix()

        mergemodule_path = Path(self.output_dir / sources[0]).absolute()
        if mergemodule_path.exists():
            raise RuntimeError(f'Merge module manifest {mergemodule_path} already exists')
        mergemodule.write(mergemodule_path.as_posix())

        # Insert rules
        Candle().compile(writer, sources, wixobj, implicit_wixobjs, implicit_deps)

        # Render deliverables
        if self.package.wix_use_fragment:
            path = wixobj
        else:
            wixobjs = [wixobj]
            wixobjs.extend(implicit_wixobjs)
            path = Light().compile(writer, wixobjs, package_name, merge_module=True)

        return path

    def _package_name(self, version):
        if self.config.variants.uwp:
            platform = 'uwp'
        elif self.config.variants.visualstudio:
            platform = 'msvc'
        else:
            platform = 'mingw'
        if self.config.variants.visualstudio and self.config.variants.vscrt == 'mdd':
            platform += '+debug'
        return '-'.join((self.package.name, platform, self.config.target_arch, version))


class MSIWithNinjaPackager(PackagerBase):
    UI_EXT = ['-ext', 'WixUIExtension']
    UTIL_EXT = ['-ext', 'WixUtilExtension']

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self._with_wine = config.platform != Platform.WINDOWS
        self.wix_prefix = get_wix_prefix(config)

    def pack(self, output_dir, devel=False, force=False, keep_temp=False):
        """
        Create the scroll of incantation and then call Ninja to assemble it
        """

        PackagerBase.pack(self, output_dir, devel, force, keep_temp)
        # This is the directory where Ninja will run
        output_dir = Path(output_dir).absolute()
        self.output_dir = Path(tempfile.mkdtemp(prefix=f'msi-{self._package_name()}-'))
        # These are the outputs of the Ninja process
        # All the paths must be understood relative to self.output_dir
        paths: list[Path] = []
        tmp_dirs: list[Path] = []

        self.merge_modules: dict[str, list[str]] = {}

        # Calm Git if you're running this interactively
        with (self.output_dir / '.gitignore').open('w', encoding='utf-8') as f:
            f.write('*\n')

        # Set Ninja build file up
        m.action(f'Creating Ninja project for MSI {self._package_name()}')
        with (self.output_dir / 'build.ninja').open('w', encoding='utf-8') as rules:
            writer = Writer(rules, width=120)

            writer.comment(f'This is the build file for the MSI installer "{self._package_name()}"')
            writer.comment('It is autogenerated by Cerbero.')
            writer.comment('Do not edit by hand.')
            writer.newline()
            writer._line('ninja_required_version = 1.1')
            writer.newline()

            # Set Candle and Light rules up
            writer.comment('Incantations for the WiX Toolkit')
            Candle.rule(writer, self.wix_prefix, self._with_wine)
            Light.rule(writer, self.wix_prefix, self._with_wine)
            StripRule.rule(writer, self.config)

            # set rules for runtime package
            writer.comment('Incantations for the runtime package generation')
            p, d = self._create_msi_installer(writer, PackageType.RUNTIME)
            paths.append(p)
            tmp_dirs.extend(d)

            # set rules for devel package
            if devel and not isinstance(self.package, App):
                writer.comment('Incantations for the development package generation')
                p, d = self._create_msi_installer(writer, PackageType.DEVEL)
                paths.append(p)
                tmp_dirs.extend(d)

            writer.close()

        # Execute ninja on the chosen output directory
        m.action(f'Building {self._package_name()} in {self.output_dir}')

        # Ensure all the WiX temporary files are reaped at the end of execution
        with tempfile.TemporaryDirectory(prefix='wix-') as tmp:
            env = self.config.env.copy()
            env['TMP'] = tmp
            shell.new_call(['ninja'], cmd_dir=self.output_dir, env=env)

        # Copy the outputs to the output directory
        for p in paths:
            src = self.output_dir / p
            dst = output_dir / p
            m.action(f'Moving {p} to {output_dir}')
            shutil.move(src, dst)

        # Create zip with Merge Modules
        if not self.package.wix_use_fragment:
            self.package.set_mode(PackageType.RUNTIME)
            zipf_path = output_dir / f'{self._package_name()}-merge-modules.zip'
            with ZipFile(zipf_path, 'w') as zipf:
                for p in self.merge_modules[PackageType.RUNTIME]:
                    zipf.write(self.output_dir / p, f'{self._package_name()}/{p}')
                zipf.write(self.output_dir / 'build.ninja', f'{self._package_name()}/build.ninja')

        # Get rid of all the Merge Modules
        # And clean up the relevant stripped directories
        # (they're all within output_dir now)
        if keep_temp:
            m.action(f'Temporary build directory is at {self.output_dir}')
        else:
            shutil.rmtree(self.output_dir)

        return paths

    def _package_name(self):
        if self.config.variants.uwp:
            platform = 'uwp'
        elif self.config.variants.visualstudio:
            platform = 'msvc'
        else:
            platform = 'mingw'
        if self.config.variants.visualstudio and self.config.variants.vscrt == 'mdd':
            platform += '+debug'
        return '-'.join((self.package.name, platform, self.config.target_arch, self.package.version))

    def _create_msi_installer(self, writer: Writer, package_type) -> tuple[Path, list[Path]]:
        self.package.set_mode(package_type)
        self.packagedeps = self.store.get_package_deps(self.package, True)
        if isinstance(self.package, App):
            self.packagedeps = [self.package]
        tmp_dirs = self._create_merge_modules(writer, package_type)
        config_path = self._create_config()
        return (self._create_msi(writer, config_path), tmp_dirs)

    def _create_merge_modules(self, writer: Writer, package_type: PackageType) -> list[Path]:
        packagedeps = {}
        tmp_dirs = []
        for package in self.packagedeps:
            package.set_mode(package_type)
            package.wix_use_fragment = self.package.wix_use_fragment
            m.action('Creating Merge Module for %s' % package)
            packager = MergeModuleWithNinjaPackager(self.config, package, self.store)
            tmpdir = packager.strip_files(package_type, self.force)
            # FIXME: this should be passed correctly
            packager.output_dir = self.output_dir
            path = packager.create_merge_module(
                writer, package_type, self.force, self.package.version, stripped_dir=tmpdir
            )
            if path:
                packagedeps[package] = path
                if tmpdir:
                    tmp_dirs.append(tmpdir)
        self.packagedeps = packagedeps
        self.merge_modules[package_type] = list(packagedeps.values())
        return tmp_dirs

    def _create_config(self):
        config = WixConfig(self.config, self.package)
        config_path = config.write(self.output_dir)
        return config_path

    def _create_msi(self, writer: Writer, config_path) -> Path:
        sources = []
        wixobjs = []

        # Make the MSI manifest relative to the Ninja root.
        msi_manifest = f'{self._package_name()}.wxs'
        # Writes the manifest for the MSI installer.
        MSI(self.config, self.package, self.packagedeps, config_path, self.store).write(
            (self.output_dir / msi_manifest).as_posix()
        )
        sources.append(msi_manifest)
        sources.append((Path(self.config.data_dir).absolute() / 'wix' / 'utils.wxs').as_posix())

        # List the object files that Candle will generate.
        # (Again, relative to the output_dir)
        wixobj = f'{self._package_name()}.msi.d/{self._package_name()}.wixobj'

        implicit_wixobjs = [f'{self._package_name()}.msi.d/utils.wixobj']

        # Insert the rules into the Ninja file.
        Candle().compile(writer, sources, wixobj, implicit_wixobjs)

        wixobjs = [wixobj]
        wixobjs.extend(implicit_wixobjs)
        if self.package.wix_use_fragment:
            wixobjs.extend(self.merge_modules[self.package.package_mode])
            implicit_deps = []
        else:
            implicit_deps = self.merge_modules[self.package.package_mode]

        path = Light([*self.UI_EXT, *self.UTIL_EXT]).compile(
            writer, wixobjs, self._package_name(), implicit_deps=implicit_deps
        )

        return path


class Packager(object):
    def __new__(klass, config, package, store):
        if isinstance(package, Package):
            return MergeModuleWithNinjaPackager(config, package, store)
        else:
            return MSIWithNinjaPackager(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro

    register_packager(Distro.WINDOWS, Packager)
