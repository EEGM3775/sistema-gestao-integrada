package com.funcoesodm.javaservice.service;

import com.funcoesodm.javaservice.dto.ImageUploadResponseDto;
import com.funcoesodm.javaservice.dto.ProjectImageDto;
import com.funcoesodm.javaservice.model.Project;
import com.funcoesodm.javaservice.model.ProjectImage;
import com.funcoesodm.javaservice.repository.ProjectImageRepository;
import com.funcoesodm.javaservice.repository.ProjectRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class ProjectImageService {

    private static final Logger logger = LoggerFactory.getLogger(ProjectImageService.class);

    private static final Set<String> ALLOWED_CONTENT_TYPES = Set.of(
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/tiff",
            "image/tif"
    );

    @Value("${app.upload.dir:./uploads}")
    private String uploadDir;

    private final ProjectImageRepository imageRepository;
    private final ProjectRepository projectRepository;
    private final UploadLimitsService uploadLimitsService;

    public ProjectImageService(ProjectImageRepository imageRepository, 
                               ProjectRepository projectRepository,
                               UploadLimitsService uploadLimitsService) {
        this.imageRepository = imageRepository;
        this.projectRepository = projectRepository;
        this.uploadLimitsService = uploadLimitsService;
    }

    @Transactional
    public ImageUploadResponseDto uploadImages(Long projectId, List<MultipartFile> files, String username) {
        logger.info("Uploading {} images to project {}", files.size(), projectId);

        long maxFileSizeBytes = uploadLimitsService.getMaxFileSizeBytesForUser(username);
        long maxRequestSizeBytes = uploadLimitsService.getMaxRequestSizeBytesForUser(username);

        long totalSizeBytes = files.stream().mapToLong(MultipartFile::getSize).sum();
        if (totalSizeBytes > maxRequestSizeBytes) {
            throw new IllegalArgumentException("Total do upload excede o limite configurado pelo usuário");
        }

        Project project = projectRepository.findById(projectId)
                .orElseThrow(() -> new RuntimeException("Project not found: " + projectId));

        List<ProjectImageDto> uploadedImages = new ArrayList<>();
        List<String> errors = new ArrayList<>();

        // Create project directory if not exists
        Path projectDir = Paths.get(uploadDir, "projects", projectId.toString(), "images");
        try {
            Files.createDirectories(projectDir);
        } catch (IOException e) {
            logger.error("Failed to create upload directory", e);
            throw new RuntimeException("Failed to create upload directory: " + e.getMessage());
        }

        for (MultipartFile file : files) {
            try {
                validateFile(file, maxFileSizeBytes);
                ProjectImage image = saveImage(file, project, projectDir);
                uploadedImages.add(ProjectImageDto.fromEntity(image));
                logger.debug("Successfully uploaded: {}", file.getOriginalFilename());
            } catch (Exception e) {
                String errorMsg = String.format("Failed to upload %s: %s", 
                        file.getOriginalFilename(), e.getMessage());
                errors.add(errorMsg);
                logger.warn(errorMsg);
            }
        }

        // Update project image count
        long imageCount = imageRepository.countByProjectId(projectId);
        project.setImageCount((int) imageCount);
        projectRepository.save(project);

        logger.info("Upload complete for project {}: {} success, {} failed", 
                projectId, uploadedImages.size(), errors.size());

        return new ImageUploadResponseDto(
                uploadedImages.size(),
                errors.size(),
                uploadedImages,
                errors
        );
    }

    private void validateFile(MultipartFile file, long maxFileSizeBytes) {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("File is empty");
        }

        if (file.getSize() > maxFileSizeBytes) {
            long maxMb = maxFileSizeBytes / (1024L * 1024L);
            throw new IllegalArgumentException("File exceeds maximum size of " + maxMb + "MB");
        }

        String contentType = file.getContentType();
        if (contentType == null || !ALLOWED_CONTENT_TYPES.contains(contentType.toLowerCase())) {
            throw new IllegalArgumentException("Invalid file type. Allowed: JPEG, PNG, TIFF");
        }
    }

    private ProjectImage saveImage(MultipartFile file, Project project, Path projectDir) throws IOException {
        // Generate unique filename
        String originalFilename = file.getOriginalFilename();
        String extension = getFileExtension(originalFilename);
        String uniqueFilename = UUID.randomUUID().toString() + extension;

        // Save file to disk
        Path filePath = projectDir.resolve(uniqueFilename);
        Files.copy(file.getInputStream(), filePath, StandardCopyOption.REPLACE_EXISTING);

        // Save metadata to database
        ProjectImage image = new ProjectImage();
        image.setFilename(uniqueFilename);
        image.setOriginalFilename(originalFilename);
        image.setContentType(file.getContentType());
        image.setFileSize(file.getSize());
        image.setStoragePath(filePath.toString());
        image.setProject(project);
        image.setTenantId(project.getTenantId()); // Fase 8.5: tenant herdado do projeto-pai

        return imageRepository.save(image);
    }

    private String getFileExtension(String filename) {
        if (filename == null || !filename.contains(".")) {
            return "";
        }
        return filename.substring(filename.lastIndexOf("."));
    }

    @Transactional(readOnly = true)
    public List<ProjectImageDto> getProjectImages(Long projectId) {
        logger.debug("Fetching images for project {}", projectId);
        return imageRepository.findByProjectId(projectId)
                .stream()
                .map(ProjectImageDto::fromEntity)
                .collect(Collectors.toList());
    }

    @Transactional
    public void deleteImage(Long imageId) {
        ProjectImage image = imageRepository.findById(imageId)
                .orElseThrow(() -> new RuntimeException("Image not found: " + imageId));

        // Delete file from disk
        try {
            Path filePath = Paths.get(image.getStoragePath());
            Files.deleteIfExists(filePath);
        } catch (IOException e) {
            logger.warn("Failed to delete file from disk: {}", image.getStoragePath());
        }

        // Delete from database
        imageRepository.delete(image);

        // Update project image count
        Long projectId = image.getProject().getId();
        long imageCount = imageRepository.countByProjectId(projectId);
        Project project = projectRepository.findById(projectId).orElseThrow();
        project.setImageCount((int) imageCount);
        projectRepository.save(project);

        logger.info("Deleted image {} from project {}", imageId, projectId);
    }

    @Transactional
    public void deleteAllProjectImages(Long projectId) {
        List<ProjectImage> images = imageRepository.findByProjectId(projectId);

        // Delete files from disk
        for (ProjectImage image : images) {
            try {
                Path filePath = Paths.get(image.getStoragePath());
                Files.deleteIfExists(filePath);
            } catch (IOException e) {
                logger.warn("Failed to delete file: {}", image.getStoragePath());
            }
        }

        // Delete from database
        imageRepository.deleteByProjectId(projectId);

        // Update project image count
        Project project = projectRepository.findById(projectId).orElseThrow();
        project.setImageCount(0);
        projectRepository.save(project);

        logger.info("Deleted all images from project {}", projectId);
    }

    public Resource getImageThumbnail(Long imageId) throws IOException {
        ProjectImage image = imageRepository.findById(imageId)
                .orElseThrow(() -> new RuntimeException("Image not found: " + imageId));
        
        Path imagePath = Paths.get(image.getStoragePath());
        if (!Files.exists(imagePath)) {
            throw new IOException("Image file not found: " + imagePath);
        }
        
        return new FileSystemResource(imagePath);
    }
}
